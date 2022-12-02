# standard imports
import json
import logging
from typing import Tuple

# external imports
import celery
import i18n
from chainlib.hash import strip_0x
from cic_types.models.person import get_contact_data_from_vcard, generate_vcard_from_contact_data, manage_identity_data

# local imports
from cic_ussd.account.chain import Chain
from cic_ussd.account.maps import gender, twenty_thousand_band, thirty_five_thousand_band, above_thirty_five_thousand_band
from cic_ussd.account.metadata import get_cached_preferred_language, UssdMetadataPointer
from cic_ussd.cache import cache_data_key, get_cached_data
from cic_ussd.db.models.account import Account, create
from cic_ussd.db.models.survey_response import SurveyResponse
from cic_ussd.db.models.base import SessionBase
from cic_ussd.error import MetadataNotFoundError
from cic_ussd.metadata import PersonMetadata
from cic_ussd.session.ussd_session import save_session_data
from cic_ussd.state_machine.logic.language import preferred_langauge_from_selection
from cic_ussd.translation import translation_for
from sqlalchemy.orm.session import Session
from cic_ussd.phone_number import E164Format
from cic_ussd.state_machine.logic.survey import parse_expenditure_band
from cic_ussd.worker import Worker
from cic_ussd.db.enum import OrganizationTag


logg = logging.getLogger(__file__)


def update_account_status_to_active(state_machine_data: Tuple[str, dict, Account, Session]):
    """This function sets user's account to active.
    :param state_machine_data: A tuple containing user input, a ussd session and user object.
    :type state_machine_data: tuple
    """
    user_input, ussd_session, account, session = state_machine_data
    session = SessionBase.bind_session(session=session)
    password = ussd_session.get('data').get('initial_pin')
    account.create_password(password)
    account.activate_account()
    session.add(account)
    session.flush()
    SessionBase.release_session(session=session)


def parse_gender(account: Account, user_input: str):
    """
    :param account:
    :type account:
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    preferred_language = get_cached_preferred_language(account.blockchain_address)
    if not preferred_language:
        preferred_language = i18n.config.get('fallback')
    r_user_input = gender().get(user_input)
    return translation_for(f'helpers.{r_user_input}', preferred_language)


def save_metadata_attribute_to_session_data(state_machine_data: Tuple[str, dict, Account, Session]):
    """This function saves first name data to the ussd session in the redis cache.
    :param state_machine_data: A tuple containing user input, a ussd session and user object.
    :type state_machine_data: tuple
    """
    user_input, ussd_session, account, session = state_machine_data
    session = SessionBase.bind_session(session=session)
    current_state = ussd_session.get('state')

    key = ''
    if 'given_name' in current_state:
        key = 'given_name'

    if 'date_of_birth' in current_state:
        key = 'date_of_birth'

    if 'family_name' in current_state:
        key = 'family_name'

    if 'gender' in current_state:
        key = 'gender'
        user_input = parse_gender(account, user_input)

    if 'location' in current_state:
        key = 'location'

    if 'products' in current_state:
        key = 'products'

    if ussd_session.get('data'):
        data = ussd_session.get('data')
        data[key] = user_input
    else:
        data = {
            key: user_input
        }
    save_session_data('cic-ussd', session, data, ussd_session)
    SessionBase.release_session(session)


def parse_person_metadata(account: Account, metadata: dict):
    """
    :param account:
    :type account:
    :param metadata:
    :type metadata:
    :return:
    :rtype:
    """
    set_gender = metadata.get('gender')
    given_name = metadata.get('given_name')
    family_name = metadata.get('family_name')
    email = metadata.get('email')
    dob = metadata.get('date_of_birth')
    if isinstance(dob, dict):
        date_of_birth = dob
    elif isinstance(dob, str):
        date_of_birth = {
            "year": int(dob)
        }
    else:
        date_of_birth = {}
    if isinstance(metadata.get('location'), dict):
        location = metadata.get('location')
    else:
        location = {
            "area_name": metadata.get('location')
        }
    if isinstance(metadata.get('products'), list):
        products = metadata.get('products')
    else:
        products = metadata.get('products').split(',')

    phone_number = account.phone_number
    date_registered = int(account.created.replace().timestamp())
    blockchain_address = account.blockchain_address
    chain_str = Chain.spec.__str__()

    if isinstance(metadata.get('identities'), dict):
        identities = metadata.get('identities')
    else:
        identities = manage_identity_data(
            blockchain_address=blockchain_address,
            chain_str=chain_str
        )

    return {
        "date_registered": date_registered,
        "date_of_birth": date_of_birth,
        "gender": set_gender,
        "identities": identities,
        "location": location,
        "products": products,
        "vcard": generate_vcard_from_contact_data(
            email=email,
            family_name=family_name,
            given_name=given_name,
            tel=phone_number,
            region=E164Format.region
        )
    }


def save_complete_person_metadata(state_machine_data: Tuple[str, dict, Account, Session]):
    """This function persists elements of the user metadata stored in session data
    :param state_machine_data: A tuple containing user input, a ussd session and user object.
    :type state_machine_data: tuple
    """
    user_input, ussd_session, account, session = state_machine_data
    metadata = ussd_session.get('data')
    person_metadata = parse_person_metadata(account, metadata)
    blockchain_address = account.blockchain_address
    s_create_person_metadata = celery.signature(
        'cic_ussd.tasks.metadata.create_person_metadata', [blockchain_address, person_metadata], queue=Worker.queue_name)
    s_create_person_metadata.apply_async()


def edit_user_metadata_attribute(state_machine_data: Tuple[str, dict, Account, Session]):
    """
    :param state_machine_data:
    :type state_machine_data:
    :return:
    :rtype:
    """
    user_input, ussd_session, account, session = state_machine_data
    blockchain_address = account.blockchain_address
    identifier = bytes.fromhex(strip_0x(blockchain_address))
    person_metadata = PersonMetadata(identifier)
    cached_person_metadata = person_metadata.get_cached_metadata()

    if not cached_person_metadata:
        raise MetadataNotFoundError(f'Expected user metadata but found none in cache for key: {blockchain_address}')

    person_metadata = json.loads(cached_person_metadata)
    data = ussd_session.get('data')
    contact_data = {}
    if vcard := person_metadata.get('vcard'):
        contact_data = get_contact_data_from_vcard(vcard)
        person_metadata.pop('vcard')
    given_name = data.get('given_name') or contact_data.get('given')
    family_name = data.get('family_name') or contact_data.get('family')
    date_of_birth = data.get('date_of_birth') or person_metadata.get('date_of_birth')
    set_gender = data.get('gender') or person_metadata.get('gender')
    location = data.get('location') or person_metadata.get('location')
    products = data.get('products') or person_metadata.get('products')
    if isinstance(date_of_birth, str):
        year = int(date_of_birth)
        person_metadata['date_of_birth'] = {'year': year}
    person_metadata['gender'] = set_gender
    person_metadata['given_name'] = given_name
    person_metadata['family_name'] = family_name
    if isinstance(location, str):
        location_data = person_metadata.get('location')
        location_data['area_name'] = location
        person_metadata['location'] = location_data
    person_metadata['products'] = products
    if contact_data:
        contact_data.pop('given')
        contact_data.pop('family')
        contact_data.pop('tel')
    person_metadata = {**person_metadata, **contact_data}
    parsed_person_metadata = parse_person_metadata(account, person_metadata)
    s_edit_person_metadata = celery.signature(
        'cic_ussd.tasks.metadata.create_person_metadata',
        [blockchain_address, parsed_person_metadata]
    )
    s_edit_person_metadata.apply_async(queue=Worker.queue_name)


def process_account_creation(state_machine_data: Tuple[str, dict, Account, Session]):
    """
    :param state_machine_data:
    :type state_machine_data:
    :return:
    :rtype:
    """
    user_input, ussd_session, account, session = state_machine_data
    language_selection = ussd_session.get("data")["preferred_language"]
    preferred_language = preferred_langauge_from_selection(user_input=language_selection)
    chain_str = Chain.spec.__str__()
    phone = ussd_session.get('msisdn')

    current_state = ussd_session.get('state')
    if current_state == 'twenty_thousand_band':
        user_input = parse_expenditure_band(twenty_thousand_band(), user_input)
        logg.debug(f"user input under twenty thousand: {user_input}")

    if current_state == 'thirty_five_thousand_band':
        user_input = parse_expenditure_band(thirty_five_thousand_band(), user_input)
        logg.debug(f"user input under thirty five thousand: {user_input}")

    if current_state == 'above_thirty_five_thousand_band':
        user_input = parse_expenditure_band(above_thirty_five_thousand_band(), user_input)
        logg.debug(f"user input under above thirty five thousand: {user_input}")

    full_name = ussd_session.get('data')['full_name']
    names = full_name.split(" ")
    try:
        given_name = names[0]
        family_name = "Unknown" if len(names) == 1 else names[1]
    except IndexError:
        given_name = "Unknown"
        family_name = "Unknown"

    logg.debug(f"given name is: {given_name}, family name is: {family_name}")

    key = cache_data_key(phone.encode('utf-8'), UssdMetadataPointer.ACCOUNT_VILLAGE)
    village = get_cached_data(key)

    data = ussd_session.get('data')
    account_gender = data.get('gender')
    economic_activity = data.get('economic_activity')
    monthly_expenditure = data.get('monthly_expenditure')

    metadata = {
        "given_name": given_name,
        "family_name": family_name,
        "date_of_birth": {},
        "location": ussd_session.get('data').get('selected_village'),
        "products": [],
        "gender": account_gender,
        "organization_tag": OrganizationTag.GIZ.value
    }
    create(chain_str, phone, session, preferred_language, metadata)
    logg.info('create account on {} for {}'.format(chain_str, phone))

    session = SessionBase.bind_session(session)
    survey_response = SurveyResponse(phone_number=phone,
                                     village=village,
                                     gender=account_gender,
                                     economic_activity=economic_activity,
                                     monthly_expenditure=monthly_expenditure,
                                     expenditure_band=user_input)
    session.add(survey_response)
    SessionBase.release_session(session)
