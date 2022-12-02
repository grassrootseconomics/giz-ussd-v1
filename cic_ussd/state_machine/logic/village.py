# standard imports
from typing import Tuple

# external imports
from sqlalchemy.orm.session import Session

# local imports
from cic_ussd.db.models.account import Account
from cic_ussd.session.ussd_session import save_session_data
from cic_ussd.cache import cache_data_key, cache_data
from cic_ussd.account.metadata import UssdMetadataPointer


def is_valid_village_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    """
    :param state_machine_data:
    :type state_machine_data:
    :return:
    :rtype:
    """
    user_input, ussd_session, account, session = state_machine_data
    if user_input in ['00', '11', '22']:
        return False
    user_input = int(user_input)
    return user_input in range(1, 6)


def save_village_selection(state_machine_data: Tuple[str, dict, Account, Session]):
    """
    :param state_machine_data:
    :type state_machine_data:
    :return:
    :rtype:
    """
    user_input, ussd_session, account, session = state_machine_data
    villages = {
        1: "Batoufam",
        2: "Bameka",
        3: "Fondjomokwet",
        4: "Other",
        5: "Foreke-Dschang",
        6: "Koutaba"
    }
    selected_village = villages[int(user_input)]
    # cache selected village:
    key = cache_data_key(
        identifier=ussd_session.get('msisdn').encode('utf-8'), salt=UssdMetadataPointer.ACCOUNT_VILLAGE)
    cache_data(key, selected_village)
    session_data = ussd_session.get('data') or {}
    session_data['selected_village'] = selected_village
    save_session_data('cic-ussd', session, session_data, ussd_session)


