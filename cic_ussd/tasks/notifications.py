# standard imports
import datetime
import logging
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# third-party imports
import celery

# local imports
from cic_ussd.account.tokens import get_cached_locked_account_token
from cic_ussd.account.transaction import from_wei
from cic_ussd.notifications import Notifier
from cic_ussd.phone_number import Support
from cic_ussd.time import TimezoneHandler

celery_app = celery.current_app
logg = logging.getLogger(__file__)
notifier = Notifier()


@celery_app.task
def transaction(notification_data: dict):
    role = notification_data.get('role')
    token_value = notification_data.get('token_value')
    token_symbol = notification_data.get('token_symbol')
    decimals = notification_data.get('decimals')
    amount = token_value if token_value == 0 else from_wei(decimals, token_value)
    balance = notification_data.get('display_balance')
    phone_number = notification_data.get('phone_number')
    preferred_language = notification_data.get('preferred_language')

    alt_metadata_id = notification_data.get('alt_metadata_id')
    metadata_id = notification_data.get('metadata_id')
    transaction_type = notification_data.get('transaction_type')
    timestamp = datetime.datetime.now(tz=ZoneInfo(TimezoneHandler.timezone)).strftime('%d-%m-%y, %H:%M %p')

    if transaction_type == 'tokengift':
        notifier.send_sms_notification(
            key='sms.account_successfully_created',
            phone_number=phone_number,
            preferred_language=preferred_language,
            support_phone=Support.phone_number)

        notifier.send_sms_notification(
            key='sms.terms',
            phone_number=phone_number,
            preferred_language=preferred_language
        )

    if transaction_type == 'transfer':
        if role == 'recipient':
            notifier.send_sms_notification('sms.received_tokens',
                                           phone_number=phone_number,
                                           preferred_language=preferred_language,
                                           amount=amount,
                                           token_symbol=token_symbol,
                                           tx_recipient_information=metadata_id,
                                           tx_sender_information=alt_metadata_id,
                                           timestamp=timestamp,
                                           balance=balance)
        if role == 'sender':
            notifier.send_sms_notification('sms.sent_tokens',
                                           phone_number=phone_number,
                                           preferred_language=preferred_language,
                                           amount=amount,
                                           token_symbol=token_symbol,
                                           tx_recipient_information=alt_metadata_id,
                                           tx_sender_information=metadata_id,
                                           timestamp=timestamp,
                                           balance=balance)
