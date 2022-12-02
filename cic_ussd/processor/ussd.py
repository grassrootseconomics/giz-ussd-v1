# standard imports
import json
from typing import Optional

# external imports
import celery
from sqlalchemy.orm.session import Session
from tinydb.table import Document

# local imports
from cic_ussd.account.balance import get_balances
from cic_ussd.account.chain import Chain
from cic_ussd.cache import get_cached_data
from cic_ussd.db.models.account import Account
from cic_ussd.db.models.base import SessionBase
from cic_ussd.db.models.ussd_session import UssdSession
from cic_ussd.menu.ussd_menu import UssdMenu
from cic_ussd.processor.menu import response
from cic_ussd.processor.util import latest_input, resume_last_ussd_session
from cic_ussd.session.ussd_session import create_or_update_session, persist_ussd_session
from cic_ussd.state_machine import UssdStateMachine
from cic_ussd.state_machine.logic.manager import States
from cic_ussd.validator import is_valid_response
from cic_ussd.processor.enums import ProviderUssdCodes
from cic_ussd.worker import Worker
from cic_ussd.account.tokens import get_active_token_symbol


def account_metadata_queries(blockchain_address: str):
    """This function queries the meta server for an account's associated metadata and preference settings.
    :param blockchain_address: hex value of an account's blockchain address.
    :type blockchain_address: str
    """
    s_query_person_metadata = celery.signature(
        'cic_ussd.tasks.metadata.query_person_metadata', [blockchain_address], queue=Worker.queue_name)
    s_query_person_metadata.apply_async()
    s_query_preferences_metadata = celery.signature(
        'cic_ussd.tasks.metadata.query_preferences_metadata', [blockchain_address], queue=Worker.queue_name)
    s_query_preferences_metadata.apply_async()


def handle_menu(account: Account, session: Session) -> Document:
    """
    If the account's pin is blocked, show the user the exit_pin_blocked menu, otherwise if the account's pin is not valid,
    show the user the initial_pin_entry menu, otherwise show the user the start menu

    :param account: Account - This is the account object that is associated with the phone number that is making the request
    :type account: Account
    :param session: This is the session object that is created when a user starts a session. It contains the user's session
    id, the user's phone number, the user's current menu, the user's current menu's name, the user's current menu's text,
    the user's current menu's options, the
    :type session: Session
    :return: A Document object
    """
    if account.pin_is_blocked(session):
        return UssdMenu.find_by_name('exit_pin_blocked')

    if not account.has_valid_pin(session):
        return UssdMenu.find_by_name('initial_pin_entry')

    return UssdMenu.find_by_name('start')


def get_menu(account: Account, session: Session, user_input: str, ussd_session: Optional[dict]) -> Document:
    """
    It takes in the account, session, user input and the ussd session and returns a document

    :param account: Account
    :type account: Account
    :param session: This is the session object that is passed to the function
    :type session: Session
    :param user_input: The user's input
    :type user_input: str
    :param ussd_session: This is the session data that is stored in the database
    :type ussd_session: Optional[dict]
    :return: A document
    """
    user_input = latest_input(user_input)
    if not ussd_session:
        return handle_menu(account, session)
    if user_input == '':
        if ussd_session.get("service_code") != ProviderUssdCodes.NEXAH.value:
            return UssdMenu.find_by_name(name='exit_invalid_input')
        else:
            return handle_menu(account, session)
    if user_input == '0':
        return UssdMenu.parent_menu(ussd_session.get('state'))
    session = SessionBase.bind_session(session)
    state = next_state(account, session, user_input, ussd_session)
    return UssdMenu.find_by_name(state)


def handle_menu_operations(external_session_id: str, phone_number: str, queue: str, service_code: str, session, user_input: str):
    """
    It handles menu operations for a user

    :param external_session_id: The session ID of the user's session with the USSD provider
    :type external_session_id: str
    :param phone_number: The phone number of the user
    :type phone_number: str
    :param queue: The queue that the user is currently in
    :type queue: str
    :param service_code: The service code of the menu
    :type service_code: str
    :param session: This is the session object that is passed to the function
    :param user_input: The user's input
    :type user_input: str
    :return: the result of the function handle_account_menu_operations
    """
    session = SessionBase.bind_session(session=session)
    account: Account = Account.get_by_phone_number(phone_number, session)
    if not account:
        return handle_no_account_menu_operations(
            account, external_session_id, phone_number, queue, session, service_code, user_input)
    account_metadata_queries(account.blockchain_address)
    return handle_account_menu_operations(account, external_session_id, queue, session, service_code, user_input)


def handle_no_account_menu_operations(account: Optional[Account], external_session_id: str, phone_number: str, queue: str, session: Session, service_code: str, user_input: str):
    initial_language_selection = 'initial_language_selection'
    menu = UssdMenu.find_by_name(initial_language_selection)
    if last_ussd_session := get_cached_data(external_session_id):
        retrieved_ussd_session = json.loads(last_ussd_session)
        menu_name = retrieved_ussd_session.get('state')
        if user_input:
            last_input = latest_input(user_input)
            state = next_state(account, session, last_input, retrieved_ussd_session)
            menu = UssdMenu.find_by_name(state)
        elif menu_name not in States.non_resumable_states and menu_name != initial_language_selection:
            menu = resume_last_ussd_session(retrieved_ussd_session.get("state"))
    if last_ussd_session:
        retrieved_ussd_session = json.loads(last_ussd_session)
        ussd_session = create_or_update_session(
            external_session_id=external_session_id,
            msisdn=phone_number,
            service_code=service_code,
            state=menu.get('name'),
            session=session,
            user_input=user_input,
            data=retrieved_ussd_session.get('data') or {})
    else:
        ussd_session = create_or_update_session(
            external_session_id=external_session_id,
            msisdn=phone_number,
            service_code=service_code,
            state=menu.get('name'),
            session=session,
            user_input=user_input,
            data={})
    persist_ussd_session(external_session_id, queue)
    menu_response = response(account=account,
                             display_key=menu.get('display_key'),
                             menu_name=menu.get('name'),
                             session=session,
                             ussd_session=ussd_session.to_json())

    if service_code not in ProviderUssdCodes.NEXAH.value.split(","):
        return menu_response
    message_type = 1 if menu_response[:3] == "CON" else 2
    menu_response_object = {
        "errcode": 200,
        "data": {
            "menu": menu_response[4:],
            "msg_type": message_type,
            "msisdn": phone_number
        }
    }
    return json.dumps(menu_response_object)


def handle_account_menu_operations(account: Account,
                                   external_session_id: str,
                                   queue: str,
                                   session: Session,
                                   service_code: str,
                                   user_input: str):
    """
    :param account:
    :type account:
    :param external_session_id:
    :type external_session_id:
    :param queue:
    :type queue:
    :param session:
    :type session:
    :param service_code:
    :type service_code:
    :param user_input:
    :type user_input:
    :return:
    :rtype:
    """
    chain_str = Chain.spec.__str__()
    phone_number = account.phone_number
    token_symbol = get_active_token_symbol(account.blockchain_address)
    get_balances(address=account.blockchain_address,
                 chain_str=chain_str,
                 token_symbol=token_symbol,
                 asynchronous=True,
                 callback_param=f'{account.blockchain_address},{token_symbol}')
    if existing_ussd_session := get_cached_data(external_session_id):
        ussd_session_in_cache = json.loads(existing_ussd_session)
        menu = get_menu(account, session, user_input, ussd_session_in_cache)
        session_data = ussd_session_in_cache.get("data")
    else:
        menu = get_menu(account, session, user_input, None)
        session_data = {}
        # handle passing date from resumed state.
        if last_ussd_session := UssdSession.last_ussd_session(phone_number=phone_number, session=session):
            if last_ussd_session.state == menu.get("name") and last_ussd_session.data:
                session_data = last_ussd_session.data

    ussd_session = create_or_update_session(
        external_session_id, phone_number, service_code, user_input, menu.get('name'), session, session_data)
    menu_response = response(
        account, menu.get('display_key'), menu.get('name'), session, ussd_session.to_json())

    if not is_valid_response(menu_response):
        raise ValueError(f'Invalid response: {menu_response}')
    persist_ussd_session(external_session_id, queue)
    if service_code not in ProviderUssdCodes.NEXAH.value.split(","):
        return menu_response
    message_type = 1 if menu_response[:3] == "CON" else 2
    menu_response_object = {
        "errcode": 200,
        "data": {
            "menu": menu_response[4:],
            "msg_type": message_type,
            "msisdn": phone_number
        }
    }
    return json.dumps(menu_response_object)


def next_state(account: Account, session, user_input: str, ussd_session: dict) -> str:
    """
    :param account:
    :type account:
    :param session:
    :type session:
    :param user_input:
    :type user_input:
    :param ussd_session:
    :type ussd_session:
    :return:
    :rtype:
    """
    state_machine = UssdStateMachine(ussd_session=ussd_session)
    state_machine.scan_data((user_input, ussd_session, account, session))
    return state_machine.state
