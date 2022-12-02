# standard imports
import datetime

# external imports
import celery
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# local imports
from cic_ussd.account.transaction import from_wei
from cic_ussd.phone_number import Support
from cic_ussd.translation import translation_for
from cic_ussd.time import TimezoneHandler


# tests imports


def test_transaction(cache_default_token_data,
                     cache_token_data,
                     celery_session_worker,
                     load_support_phone,
                     mock_notifier_api,
                     notification_data,
                     set_locale_files):
    notification_data['transaction_type'] = 'transfer'
    notification_data['decimals'] = 6
    amount = from_wei(6, notification_data.get('token_value'))
    balance = notification_data.get('display_balance')
    phone_number = notification_data.get('phone_number')
    preferred_language = notification_data.get('preferred_language')
    token_symbol = notification_data.get('token_symbol')
    alt_metadata_id = notification_data.get('alt_metadata_id')
    metadata_id = notification_data.get('metadata_id')
    timestamp = datetime.datetime.now(tz=ZoneInfo(TimezoneHandler.timezone)).strftime('%d-%m-%y, %H:%M %p')
    s_transaction = celery.signature(
        'cic_ussd.tasks.notifications.transaction', [notification_data]
    )
    s_transaction.apply_async().get()
    assert mock_notifier_api.get('recipient') == phone_number
    message = translation_for(key='sms.sent_tokens',
                              phone_number=phone_number,
                              preferred_language=preferred_language,
                              amount=amount,
                              token_symbol=token_symbol,
                              tx_recipient_information=alt_metadata_id,
                              tx_sender_information=metadata_id,
                              timestamp=timestamp,
                              balance=balance)
    assert mock_notifier_api.get('message') == message

    notification_data['role'] = 'recipient'
    notification_data['direction_tag'] = 'From'
    notification_data['decimals'] = 6
    s_transaction = celery.signature(
        'cic_ussd.tasks.notifications.transaction', [notification_data]
    )
    s_transaction.apply_async().get()
    message = translation_for(key='sms.received_tokens',
                              phone_number=phone_number,
                              preferred_language=preferred_language,
                              amount=amount,
                              token_symbol=token_symbol,
                              tx_recipient_information=metadata_id,
                              tx_sender_information=alt_metadata_id,
                              timestamp=timestamp,
                              balance=balance)
    assert mock_notifier_api.get('message') == message

    notification_data['transaction_type'] = 'tokengift'
    notification_data['decimals'] = 6
    s_transaction = celery.signature(
        'cic_ussd.tasks.notifications.transaction', [notification_data]
    )
    s_transaction.apply_async().get()
    support_phone = Support.phone_number
    message = translation_for(key='sms.account_successfully_created',
                              preferred_language=preferred_language,
                              balance=balance,
                              support_phone=support_phone,
                              token_symbol=token_symbol)
    assert mock_notifier_api.get('message') == message
