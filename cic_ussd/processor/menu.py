# standard imports
import json
import logging

# external imports
import celery
import i18n.config
from cic_types.condiments import MetadataPointer
from sqlalchemy.orm.session import Session

# local imports
from cic_ussd.account.balance import (BalancesHandler,
                                      get_cached_display_balance)
from cic_ussd.account.chain import Chain
from cic_ussd.account.metadata import get_cached_preferred_language, UssdMetadataPointer
from cic_ussd.account.statement import (
    get_cached_statement,
    parse_statement_transactions,
    query_statement)
from cic_ussd.account.tokens import (get_active_token_symbol,
                                     get_cached_token_symbol_list,
                                     get_cached_token_data_list,
                                     parse_token_list)
from cic_ussd.cache import cache_data_key, cache_data, get_cached_data
from cic_ussd.db.models.account import Account
from cic_ussd.metadata import PersonMetadata
from cic_ussd.phone_number import Support, E164Format
from cic_ussd.processor.util import parse_person_metadata, ussd_menu_list
from cic_ussd.session.ussd_session import save_session_data
from cic_ussd.state_machine.logic.language import preferred_langauge_from_selection
from cic_ussd.translation import translation_for
from cic_ussd.worker import Worker

logg = logging.getLogger(__file__)


# It's a class that processes the menu for the account
class MenuProcessor:
    def __init__(self, account: Account, display_key: str, menu_name: str, session: Session, ussd_session: dict):
        self.account = account
        self.display_key = display_key
        if account:
            self.identifier = bytes.fromhex(self.account.blockchain_address)
        self.menu_name = menu_name
        self.session = session
        self.ussd_session = ussd_session

    def account_balances(self) -> str:
        """
        It returns a string with the available balance of the account.
        :return: The account balances of the user.
        """
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        with_available_balance = f'{self.display_key}.available_balance'
        decimals = 6
        available_balance = get_cached_display_balance(decimals, [self.identifier, token_symbol.encode('utf-8')])
        return translation_for(key=with_available_balance,
                               preferred_language=preferred_language,
                               available_balance=available_balance,
                               token_symbol=token_symbol)

    def account_statement(self) -> str:
        """
        It takes a list of transactions, splits it into 3 sets, and returns the first, middle, or last set depending on the
        display_key
        :return: The return value is a string.
        """
        cached_statement = get_cached_statement(self.account.blockchain_address)

        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')

        statement_list = []
        if cached_statement:
            statement_list = parse_statement_transactions(statement=json.loads(cached_statement))

        fallback = translation_for('helpers.no_transaction_history', preferred_language)
        transaction_sets = ussd_menu_list(fallback=fallback, menu_list=statement_list, split=3)

        if self.display_key == 'ussd.first_transaction_set':
            return translation_for(
                self.display_key, preferred_language, first_transaction_set=transaction_sets[0]
            )
        if self.display_key == 'ussd.middle_transaction_set':
            return translation_for(
                self.display_key, preferred_language, middle_transaction_set=transaction_sets[1]
            )
        if self.display_key == 'ussd.last_transaction_set':
            return translation_for(
                self.display_key, preferred_language, last_transaction_set=transaction_sets[2]
            )

    def guardian_pin_authorization(self):
        guardian_information = self.guardian_metadata()
        return self.pin_authorization(guardian_information=guardian_information)

    def guardian_list(self):
        """
        It returns a string that contains a list of the guardians of the account that is passed to it
        :return: The return value is a string.
        """
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        if set_guardians := self.account.get_guardians()[:3]:
            guardians_list = ''
            guardians_list_header = translation_for('helpers.guardians_list_header', preferred_language)
            for phone_number in set_guardians:
                guardian = Account.get_by_phone_number(phone_number, self.session)
                guardian_information = guardian.standard_metadata_id()
                guardians_list += f'{guardian_information}\n'
            guardians_list = guardians_list_header + '\n' + guardians_list
        else:
            guardians_list = translation_for('helpers.no_guardians_list', preferred_language)
        return translation_for(self.display_key, preferred_language, guardians_list=guardians_list)

    def account_tokens(self) -> str:
        """
        It takes a list of tokens, splits it into 3 sets, and returns the first, middle, or last set depending on the
        display key
        :return: The return value is a string.
        """
        cached_token_data_list = get_cached_token_data_list(self.account.blockchain_address)
        token_data_list = parse_token_list(cached_token_data_list)

        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')

        fallback = translation_for('helpers.no_tokens_list', preferred_language)
        token_list_sets = ussd_menu_list(fallback=fallback, menu_list=token_data_list, split=3)

        data = {
            'account_tokens_list': cached_token_data_list
        }
        save_session_data(data=data, queue=Worker.queue_name, session=self.session, ussd_session=self.ussd_session)

        if self.display_key == 'ussd.first_account_tokens_set':
            return translation_for(
                self.display_key, preferred_language, first_account_tokens_set=token_list_sets[0]
            )
        if self.display_key == 'ussd.middle_account_tokens_set':
            return translation_for(
                self.display_key, preferred_language, middle_account_tokens_set=token_list_sets[1]
            )
        if self.display_key == 'ussd.last_account_tokens_set':
            return translation_for(
                self.display_key, preferred_language, last_account_tokens_set=token_list_sets[2]
            )

    def help(self) -> str:
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language, support_phone=Support.phone_number)

    def person_metadata(self) -> str:
        """
        It takes a person's blockchain address, and returns a string of their metadata
        :return: A string
        """
        person_metadata = PersonMetadata(self.identifier)
        cached_person_metadata = person_metadata.get_cached_metadata()
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        if cached_person_metadata:
            return parse_person_metadata(cached_person_metadata, self.display_key, preferred_language)
        absent = translation_for('helpers.not_provided', preferred_language)
        return translation_for(
            self.display_key,
            preferred_language,
            full_name=absent,
            gender=absent,
            age=absent,
            location=absent,
            products=absent
        )

    def pin_authorization(self, **kwargs) -> str:
        """
        The function returns a string that is a translation of the key `ussd.retry_pin_entry` in the language
        `preferred_language` with the value of the variable `remaining_attempts` substituted in the string
        :return: The translation for the first pin entry or the retry pin entry.
        """
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        if self.account.failed_pin_attempts == 0:
            return translation_for(f'{self.display_key}.first', preferred_language, **kwargs)

        remaining_attempts = 3
        remaining_attempts -= self.account.failed_pin_attempts
        retry_pin_entry = translation_for(
            'ussd.retry_pin_entry', preferred_language, remaining_attempts=remaining_attempts
        )
        return translation_for(
            f'{self.display_key}.retry', preferred_language, retry_pin_entry=retry_pin_entry
        )

    def guarded_account_metadata(self):
        guarded_account_phone_number = self.ussd_session.get('data').get('guarded_account_phone_number')
        guarded_account = Account.get_by_phone_number(guarded_account_phone_number, self.session)
        return guarded_account.standard_metadata_id()

    def guardian_metadata(self):
        guardian_phone_number = self.ussd_session.get('data').get('guardian_phone_number')
        guardian = Account.get_by_phone_number(guardian_phone_number, self.session)
        return guardian.standard_metadata_id()

    def language(self):
        region = E164Format.region
        key = cache_data_key(['system:languages'.encode('utf-8'), region.encode('utf-8')], MetadataPointer.NONE)
        cached_system_languages = get_cached_data(key)
        language_list: list = json.loads(cached_system_languages)

        if self.account:
            preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        else:
            preferred_language = i18n.config.get('fallback')

        fallback = translation_for('helpers.no_language_list', preferred_language)
        language_list_sets = ussd_menu_list(fallback=fallback, menu_list=language_list, split=3)

        if self.display_key in ['ussd.initial_language_selection', 'ussd.select_preferred_language']:
            return translation_for(
                self.display_key, preferred_language, first_language_set=language_list_sets[0]
            )

        if 'middle_language_set' in self.display_key:
            return translation_for(
                self.display_key, preferred_language, middle_language_set=language_list_sets[1]
            )

        if 'last_language_set' in self.display_key:
            return translation_for(
                self.display_key, preferred_language, last_language_set=language_list_sets[2]
            )

    def initial_language_preference(self):
        if language_selection := self.ussd_session.get('data').get('preferred_language'):
            preferred_language = preferred_langauge_from_selection(language_selection)
        else:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language)

    def reset_guarded_pin_authorization(self):
        guarded_account_information = self.guarded_account_metadata()
        return self.pin_authorization(guarded_account_information=guarded_account_information)

    def start_menu(self):
        active_token_symbol = get_active_token_symbol(self.account.blockchain_address)
        key = cache_data_key([self.identifier, active_token_symbol.encode('utf-8')], MetadataPointer.BALANCES)
        balances = json.loads(get_cached_data(key))
        balance_handler = BalancesHandler(balances=balances, decimals=6)
        display_balance = balance_handler.display_balance()

        # cache spendable balance in case one wants to transfer
        spendable_balance = balance_handler.spendable_balance(chain_str=Chain.spec.__str__(),
                                                              token_symbol=active_token_symbol)
        s_key = cache_data_key([self.identifier, active_token_symbol.encode('utf-8')],
                               UssdMetadataPointer.BALANCE_SPENDABLE)

        cache_data(s_key, spendable_balance)

        # query statement asynchronously
        logg.debug(f"Querying statement for {self.account.blockchain_address}")
        query_statement(self.account.blockchain_address)

        token_symbol_list = get_cached_token_symbol_list(self.account.blockchain_address)

        # asynchronous update of balances in my vouchers list
        logg.debug(
            f"Asynchronously updating balances for all tokens: {token_symbol_list}. Account: {self.account.blockchain_address}")
        s_update_token_balances = celery.signature(
            'cic_ussd.tasks.tokens.update_account_token_balances',
            [self.account.blockchain_address, Chain.spec.__str__(), token_symbol_list],
            queue=Worker.queue_name)

        s_update_my_vouchers_list = celery.signature(
            'cic_ussd.tasks.tokens.update_my_vouchers_list',
            queue=Worker.queue_name)
        celery.chain(s_update_token_balances, s_update_my_vouchers_list).apply_async()

        # asynchronously update sink address balances
        logg.debug(f"Asynchronously updating sink address balances for all tokens: {token_symbol_list}.")
        s_update_sink_address_balances = celery.signature(
            'cic_ussd.tasks.tokens.update_sink_address_balances',
            [Chain.spec.__str__(), token_symbol_list],
            queue=Worker.queue_name)
        s_update_sink_address_balances.apply_async()

        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(
            self.display_key, preferred_language, account_balance=display_balance,
            account_token_name=active_token_symbol
        )

    def token_selection_pin_authorization(self) -> str:
        selected_token = self.ussd_session.get('data').get('selected_token')
        token_symbol = selected_token.get('symbol')
        token_issuer = selected_token.get('issuer')
        token_description = selected_token.get('description')
        if isinstance(selected_token.get('contact'), dict):
            token_contact = selected_token.get('contact').get('phone') or selected_token.get('contact').get('email')
        else:
            token_contact = selected_token.get('contact')
        token_location = selected_token.get('location')
        token_data = f'{token_symbol}\n{token_issuer}\n{token_contact}\n{token_location}\n{token_description}'
        return self.pin_authorization(token_data=token_data)

    def enter_transaction_amount(self):
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        key = cache_data_key([self.identifier, token_symbol.encode('utf-8')],
                             UssdMetadataPointer.BALANCE_SPENDABLE)
        spendable_amount = get_cached_data(key)
        return translation_for(self.display_key, preferred_language,
                               spendable_amount=f"{spendable_amount} {token_symbol}")

    def transaction_pin_authorization(self) -> str:
        recipient_phone_number = self.ussd_session.get('data').get('recipient_phone_number')
        recipient = Account.get_by_phone_number(recipient_phone_number, self.session)
        tx_recipient_information = recipient.standard_metadata_id()
        tx_sender_information = self.account.standard_metadata_id()
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        user_input = self.ussd_session.get('data').get('transaction_amount')
        return self.pin_authorization(
            recipient_information=tx_recipient_information,
            transaction_amount=user_input,
            token_symbol=token_symbol,
            sender_information=tx_sender_information
        )

    def exit_guardian_addition_success(self) -> str:
        guardian_information = self.guardian_metadata()
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key,
                               preferred_language,
                               guardian_information=guardian_information)

    def exit_guardian_removal_success(self):
        guardian_information = self.guardian_metadata()
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key,
                               preferred_language,
                               guardian_information=guardian_information)

    def exit_invalid_guardian_addition(self):
        failure_reason = self.ussd_session.get('data').get('failure_reason')
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language, error_exit=failure_reason)

    def exit_invalid_guardian_removal(self):
        failure_reason = self.ussd_session.get('data').get('failure_reason')
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language, error_exit=failure_reason)

    def exit_pin_reset_initiated_success(self):
        guarded_account_information = self.guarded_account_metadata()
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key,
                               preferred_language,
                               guarded_account_information=guarded_account_information)

    def exit_insufficient_balance(self):
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        session_data = self.ussd_session.get('data')
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        decimals = 6
        available_balance = get_cached_display_balance(decimals, [self.identifier, token_symbol.encode('utf-8')])
        transaction_amount = session_data.get('transaction_amount')
        recipient_phone_number = self.ussd_session.get('data').get('recipient_phone_number')
        recipient = Account.get_by_phone_number(recipient_phone_number, self.session)
        tx_recipient_information = recipient.standard_metadata_id()
        return translation_for(
            self.display_key,
            preferred_language,
            amount=transaction_amount,
            token_symbol=token_symbol,
            recipient_information=tx_recipient_information,
            token_balance=available_balance
        )

    def exit_invalid_menu_option(self):
        if self.account:
            preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        else:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language, support_phone=Support.phone_number)

    def exit_pin_blocked(self):
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for('ussd.exit_pin_blocked', preferred_language, support_phone=Support.phone_number)

    def exit_successful_token_selection(self) -> str:
        selected_token = self.ussd_session.get('data').get('selected_token')
        token_symbol = selected_token.get('symbol')
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        return translation_for(self.display_key, preferred_language, token_symbol=token_symbol)

    def exit_invalid_recipient(self):
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        invalid_recipient = self.ussd_session.get('user_input')
        return translation_for(self.display_key, preferred_language, invalid_number=invalid_recipient)

    def exit_successfully_invited_new_user(self):
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)

        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        invited_number = self.ussd_session.get('data').get('recipient_phone_number')
        return translation_for(self.display_key, preferred_language, invited_user=invited_number)

    def exit_successful_transaction(self):
        amount = self.ussd_session.get('data').get('transaction_amount')
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        recipient_phone_number = self.ussd_session.get('data').get('recipient_phone_number')
        recipient = Account.get_by_phone_number(phone_number=recipient_phone_number, session=self.session)
        tx_recipient_information = recipient.standard_metadata_id()
        tx_sender_information = self.account.standard_metadata_id()
        return translation_for(
            self.display_key,
            preferred_language,
            transaction_amount=amount,
            token_symbol=token_symbol,
            recipient_information=tx_recipient_information,
            sender_information=tx_sender_information
        )

    def community_fund_balances(self):
        token_symbol = get_active_token_symbol(self.account.blockchain_address)
        key = cache_data_key(token_symbol.encode("utf-8"), salt=UssdMetadataPointer.TOKEN_SINK_ADDRESS)
        balances = None
        if blockchain_address := get_cached_data(key):
            balances = get_cached_display_balance(6, [bytes.fromhex(blockchain_address), token_symbol.encode('utf-8')])
        preferred_language = get_cached_preferred_language(self.account.blockchain_address)
        if not preferred_language:
            preferred_language = i18n.config.get('fallback')
        community_fund_balance = f"{balances} {token_symbol}"
        return translation_for(self.display_key,
                               preferred_language,
                               community_fund_balance=community_fund_balance)


def response(account: Account, display_key: str, menu_name: str, session: Session, ussd_session: dict) -> str:
    """This function extracts the appropriate session data based on the current menu name. It then inserts them as
    keywords in the i18n function.
    :param account: The account in a running USSD session.
    :type account: Account
    :param display_key: The path in the translation files defining an appropriate ussd response
    :type display_key: str
    :param menu_name: The name by which a specific menu can be identified.
    :type menu_name: str
    :param session:
    :type session:
    :param ussd_session: A JSON serialized in-memory ussd session object
    :type ussd_session: dict
    :return: A string value corresponding the ussd menu's text value.
    :rtype: str
    """
    menu_processor = MenuProcessor(account, display_key, menu_name, session, ussd_session)

    if menu_name in {'enter_village_selection_first_set',
                     'enter_full_name',
                     'economic_activity_selection',
                     'monthly_expenditure_query',
                     'enter_gender',
                     'twenty_thousand_band',
                     'thirty_five_thousand_band',
                     'above_thirty_five_thousand_band',
                     'account_creation_prompt'}:
        return menu_processor.initial_language_preference()

    if menu_name == 'start':
        return menu_processor.start_menu()

    if menu_name == 'help':
        return menu_processor.help()

    if menu_name == 'transaction_pin_authorization':
        return menu_processor.transaction_pin_authorization()

    if menu_name == 'token_selection_pin_authorization':
        return menu_processor.token_selection_pin_authorization()

    if menu_name == 'exit_invalid_recipient':
        return menu_processor.exit_invalid_recipient()

    if menu_name == 'exit_successfully_invited_new_user':
        return menu_processor.exit_successfully_invited_new_user()

    if menu_name == 'exit_insufficient_balance':
        return menu_processor.exit_insufficient_balance()

    if menu_name == 'exit_invalid_guardian_addition':
        return menu_processor.exit_invalid_guardian_addition()

    if menu_name == 'exit_invalid_guardian_removal':
        return menu_processor.exit_invalid_guardian_removal()

    if menu_name == 'exit_successful_transaction':
        return menu_processor.exit_successful_transaction()

    if menu_name == 'exit_guardian_addition_success':
        return menu_processor.exit_guardian_addition_success()

    if menu_name == 'exit_guardian_removal_success':
        return menu_processor.exit_guardian_removal_success()

    if menu_name == 'exit_pin_reset_initiated_success':
        return menu_processor.exit_pin_reset_initiated_success()

    if menu_name == "community_fund_balances":
        return menu_processor.community_fund_balances()

    if menu_name == 'account_balances':
        return menu_processor.account_balances()

    if menu_name == 'guardian_list':
        return menu_processor.guardian_list()

    if 'guardian_pin_authorization' in menu_name:
        return menu_processor.guardian_pin_authorization()

    if menu_name == 'reset_guarded_pin_authorization':
        return menu_processor.reset_guarded_pin_authorization()

    if 'pin_authorization' in menu_name:
        return menu_processor.pin_authorization()

    if 'enter_current_pin' in menu_name:
        return menu_processor.pin_authorization()

    if 'transaction_set' in menu_name:
        return menu_processor.account_statement()

    if 'account_tokens_set' in menu_name:
        return menu_processor.account_tokens()

    if 'language' in menu_name:
        return menu_processor.language()

    if menu_name == 'display_user_metadata':
        return menu_processor.person_metadata()

    if menu_name == 'exit_invalid_menu_option':
        return menu_processor.exit_invalid_menu_option()

    if menu_name == 'exit_pin_blocked':
        return menu_processor.exit_pin_blocked()

    if menu_name == 'exit_successful_token_selection':
        return menu_processor.exit_successful_token_selection()

    if menu_name == "enter_transaction_amount":
        return menu_processor.enter_transaction_amount()

    preferred_language = i18n.config.get('fallback')
    if account:
        preferred_language = get_cached_preferred_language(account.blockchain_address)

    return translation_for(display_key, preferred_language)
