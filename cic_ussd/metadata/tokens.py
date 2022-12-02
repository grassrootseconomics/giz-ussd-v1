# standard imports
from typing import Dict, Optional

# external imports
import json

from cic_types.condiments import MetadataPointer

# local imports
from .base import UssdMetadataHandler
from cic_ussd.cache import cache_data
from cic_ussd.error import MetadataNotFoundError


class TokenMetadata(UssdMetadataHandler):
    def __init__(self, identifier: bytes, **kwargs):
        super(TokenMetadata, self).__init__(identifier=identifier, **kwargs)


def token_metadata_handler(metadata_client: TokenMetadata) -> Optional[Dict]:
    """
    > The function takes a `TokenMetadata` object and returns a dictionary of metadata

    :param metadata_client: TokenMetadata
    :type metadata_client: TokenMetadata
    :return: A dictionary of metadata
    """
    result = metadata_client.query()
    token_metadata = result.json()
    if not token_metadata:
        raise MetadataNotFoundError(f'No metadata found at: {metadata_client.metadata_pointer} for: {metadata_client.identifier.decode("utf-8")}')
    cache_data(metadata_client.metadata_pointer, json.dumps(token_metadata))
    return token_metadata


def query_token_metadata(identifier: bytes):
    """
    `query_token_metadata` takes a token identifier and returns the token metadata

    :param identifier: The token's identifier
    :type identifier: bytes
    :return: The token metadata is being returned.
    """
    token_metadata_client = TokenMetadata(identifier=identifier, cic_type=MetadataPointer.TOKEN_META_SYMBOL)
    return token_metadata_handler(token_metadata_client)


def query_token_info(identifier: bytes):
    """
    `query_token_info` is a function that takes a token identifier as input and returns the token metadata

    :param identifier: The identifier of the token you want to query
    :type identifier: bytes
    :return: The token metadata
    """
    token_info_client = TokenMetadata(identifier=identifier, cic_type=MetadataPointer.TOKEN_PROOF_SYMBOL)
    return token_metadata_handler(token_info_client)
