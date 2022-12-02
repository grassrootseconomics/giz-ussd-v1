# standard imports
import datetime
import json
import logging
from typing import List

# external imports
from cic_types.models.person import get_contact_data_from_vcard
from tinydb.table import Document

# local imports
from cic_ussd.menu.ussd_menu import UssdMenu
from cic_ussd.state_machine.logic.manager import States
from cic_ussd.translation import translation_for

logg = logging.getLogger(__file__)


def latest_input(user_input: str) -> str:
    """
    :param user_input:
    :return:
    """
    return user_input.split('*')[-1]


def parse_person_metadata(cached_metadata: str, display_key: str, preferred_language: str) -> str:
    """This function extracts person metadata formatted to suite display on the ussd interface.
    :param cached_metadata: Person metadata JSON str.
    :type cached_metadata: str
    :param display_key: Path to an entry in menu data in translation files.
    :type display_key: str
    :param preferred_language: An account's set preferred language.
    :type preferred_language: str
    :return:
    :rtype:
    """
    user_metadata = json.loads(cached_metadata)
    contact_data = get_contact_data_from_vcard(user_metadata.get('vcard'))
    given_name = contact_data.get("given")
    family_name = contact_data.get("family")
    date_of_birth = user_metadata.get('date_of_birth')
    if date_of_birth and len(date_of_birth.items()) > 0:
        year_of_birth = date_of_birth.get('year')
        present_year = datetime.datetime.now().year
        age = present_year - year_of_birth
    else:
        age = None
    gender = user_metadata.get('gender')
    products = ', '.join(user_metadata.get('products'))
    location = user_metadata.get('location').get('area_name')

    absent = translation_for('helpers.not_provided', preferred_language)
    person_metadata = [given_name, family_name, age, gender, location, products]
    person_metadata = [absent if elem is None else elem for elem in person_metadata]

    full_name = f'{person_metadata[0]} {person_metadata[1]}'

    return translation_for(
        key=display_key,
        preferred_language=preferred_language,
        full_name=full_name,
        age=person_metadata[2],
        gender=person_metadata[3],
        location=person_metadata[4],
        products=person_metadata[5]
    )


def resume_last_ussd_session(last_state: str) -> Document:
    """
    :param last_state:
    :type last_state:
    :return:
    :rtype:
    """

    if last_state in States.non_resumable_states:
        return UssdMenu.find_by_name('start')
    return UssdMenu.find_by_name(last_state)


def ussd_menu_list(fallback: str, menu_list: list, split: int = 3) -> List[str]:
    """
    :param fallback:
    :type fallback:
    :param menu_list:
    :type menu_list:
    :param split:
    :type split:
    :return:
    :rtype:
    """
    menu_list_sets = [menu_list[item:item + split] for item in range(0, len(menu_list), split)]
    menu_list_reprs = []
    for i in range(split):
        try:
            menu_list_reprs.append(''.join(f'{list_set_item}\n' for list_set_item in menu_list_sets[i]).rstrip('\n'))
        except IndexError:
            menu_list_reprs.append(fallback)
    return menu_list_reprs

