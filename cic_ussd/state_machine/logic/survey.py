# standard imports
import logging
from typing import Tuple

# external imports
import i18n
from sqlalchemy.orm.session import Session

# local imports
from cic_ussd.account.maps import (economic_activity,
                                   monthly_expenditure,
                                   gender,
                                   twenty_thousand_band,
                                   thirty_five_thousand_band,
                                   above_thirty_five_thousand_band)
from cic_ussd.db.models.account import Account
from cic_ussd.db.models.base import SessionBase
from cic_ussd.session.ussd_session import save_session_data
from cic_ussd.translation import translation_for
from cic_ussd.state_machine.logic.language import preferred_langauge_from_selection

logg = logging.getLogger(__file__)


def account_preferred_language(ussd_session: dict):
    """
    :return:
    :rtype:
    """
    language_selection = ussd_session.get("data")["preferred_language"]
    return preferred_langauge_from_selection(user_input=language_selection)


def parse_economic_activity(user_input: str, ussd_session: dict):
    """
    :param ussd_session:
    :type ussd_session:
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    preferred_language = account_preferred_language(ussd_session)
    r_user_input = economic_activity().get(user_input)
    return translation_for(f'helpers.{r_user_input}', preferred_language)


def parse_gender(user_input: str, ussd_session: dict):
    """
    :param ussd_session:
    :type ussd_session:
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    preferred_language = account_preferred_language(ussd_session)
    r_user_input = gender().get(user_input)
    return translation_for(f'helpers.{r_user_input}', preferred_language)


def parse_monthly_expenditure(user_input: str):
    """
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    return monthly_expenditure().get(user_input)


def parse_expenditure_band(band: dict, user_input: str):
    """
    :param band:
    :type band:
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    return band.get(user_input)


def is_valid_economic_activity_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    user_input, ussd_session, account, session = state_machine_data
    return user_input in economic_activity().keys()


def is_valid_monthly_expenditure_answer(state_machine_data: Tuple[str, dict, Account, Session]):
    user_input, ussd_session, account, session = state_machine_data
    return user_input in monthly_expenditure().keys()


def is_valid_expenditure_selection(band: dict, user_input: str) -> bool:
    return user_input in band


def is_valid_twenty_thousand_band_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    user_input, ussd_session, account, session = state_machine_data
    return is_valid_expenditure_selection(twenty_thousand_band(), user_input)


def is_valid_thirty_five_thousand_band_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    user_input, ussd_session, account, session = state_machine_data
    return is_valid_expenditure_selection(thirty_five_thousand_band(), user_input)


def is_valid_above_thirty_five_thousand_band_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    user_input, ussd_session, account, session = state_machine_data
    return is_valid_expenditure_selection(above_thirty_five_thousand_band(), user_input)


def save_survey_entry(state_machine_data: Tuple[str, dict, Account, Session]):
    """This function saves first name data to the ussd session in the redis cache.
    :param state_machine_data: A tuple containing user input, an ussd session and user object.
    :type state_machine_data: tuple
    """
    user_input, ussd_session, account, session = state_machine_data
    session = SessionBase.bind_session(session=session)
    current_state = ussd_session.get('state')

    key = ''
    if 'full_name' in current_state:
        key = 'full_name'

    if 'gender' in current_state:
        key = 'gender'
        user_input = parse_gender(user_input, ussd_session)

    if 'economic_activity' in current_state:
        key = 'economic_activity'
        user_input = parse_economic_activity(user_input, ussd_session)

    if 'monthly_expenditure' in current_state:
        key = 'monthly_expenditure'
        user_input = parse_monthly_expenditure(user_input)

    if ussd_session.get('data'):
        data = ussd_session.get('data')
        data[key] = user_input
    else:
        data = {
            key: user_input
        }

    save_session_data('cic-ussd', session, data, ussd_session)
    SessionBase.release_session(session)
