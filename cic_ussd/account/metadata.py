# standard imports
import enum
import json
import logging
from typing import Optional

# external imports
from cic_types.models.person import Person
from cic_types.condiments import MetadataPointer

# local imports
from cic_ussd.metadata import PreferencesMetadata

logg = logging.getLogger(__name__)


def get_cached_preferred_language(blockchain_address: str) -> Optional[str]:
    """This function retrieves an account's set preferred language from preferences metadata in redis cache.
    :param blockchain_address:
    :type blockchain_address:
    :return: Account's set preferred language | Fallback preferred language.
    :rtype: str
    """
    identifier = bytes.fromhex(blockchain_address)
    preferences_metadata_handler = PreferencesMetadata(identifier)
    if cached_preferences_metadata := preferences_metadata_handler.get_cached_metadata():
        preferences_metadata = json.loads(cached_preferences_metadata)
        return preferences_metadata.get('preferred_language')
    return None


def parse_account_metadata(account_metadata: dict) -> str:
    """
    :param account_metadata:
    :type account_metadata:
    :return:
    :rtype:
    """
    person = Person()
    deserialized_person = person.deserialize(person_data=account_metadata)
    given_name = deserialized_person.given_name
    family_name = deserialized_person.family_name
    phone_number = deserialized_person.tel
    unknown = "Unknown"
    unique_tag = ""
    if given_name != unknown:
        unique_tag += f"{given_name} "

    if family_name != unknown:
        unique_tag += f"{family_name} "

    unique_tag += phone_number
    return unique_tag


class UssdMetadataPointer(enum.Enum):
    BALANCE_SPENDABLE = ":cic.balance.adjusted_spendable"
    LOCKED_ACCOUNT_TOKEN = ":cic.account.locked_account_token"
    COMMUNITY_FUND_BALANCE = ":cic.account.community_fund_balance"
    TOKEN_SINK_ADDRESS = ":cic.token.sink.address"
    ACCOUNT_VILLAGE = "cic.account.village"
