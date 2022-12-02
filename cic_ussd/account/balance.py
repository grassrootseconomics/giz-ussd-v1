# standard imports
import json
import logging
from typing import Union, Optional

# third-party imports
from cic_eth.api import Api
from cic_eth_aux.erc20_demurrage_token.api import Api as DemurrageApi
from cic_types.condiments import MetadataPointer

# local imports
from cic_ussd.account.transaction import from_wei
from cic_ussd.cache import cache_data_key, get_cached_data
from cic_ussd.error import CachedDataNotFoundError
from cic_ussd.worker import Worker

logg = logging.getLogger(__file__)


def get_balances(address: str,
                 chain_str: str,
                 token_symbol: str,
                 asynchronous: bool = False,
                 callback_param: any = None,
                 callback_queue='giz-cic-ussd',
                 callback_task='cic_ussd.tasks.callback_handler.balances_callback') -> Optional[list]:
    """This function queries cic-eth for an account's balances, It provides a means to receive the balance either
    asynchronously or synchronously. It returns a dictionary containing the network, outgoing and incoming balances.
    :param address: Ethereum address of an account.
    :type address: str, 0x-hex
    :param chain_str: The chain name and network id.
    :type chain_str: str
    :param asynchronous: Boolean value checking whether to return balances asynchronously.
    :type asynchronous: bool
    :param callback_param: Data to be sent along with the callback containing balance data.
    :type callback_param: any
    :param callback_queue:
    :type callback_queue:
    :param callback_task: A celery task path to which callback data should be sent.
    :type callback_task: str
    :param token_symbol: ERC20 token symbol of the account whose balance is being queried.
    :type token_symbol: str
    :return: A list containing balance data if called synchronously. | None
    :rtype: list | None
    """
    logg.debug(f'retrieving {token_symbol} balance for address: {address}')
    if asynchronous:
        cic_eth_api = Api(
            chain_str=chain_str,
            callback_queue=callback_queue,
            callback_task=callback_task,
            callback_param=callback_param
        )
        cic_eth_api.balance(address=address, token_symbol=token_symbol)
    else:
        cic_eth_api = Api(chain_str=chain_str)
        balance_request_task = cic_eth_api.balance(
            address=address,
            token_symbol=token_symbol)
        return balance_request_task.get()


class BalancesHandler:
    def __init__(self, balances: dict, decimals: int):
        self.decimals = decimals
        self.incoming_balance = balances.get('balance_incoming')
        self.network_balance = balances.get('balance_network')
        self.outgoing_balance = balances.get('balance_outgoing')

    def display_balance(self) -> float:
        """This function calculates an account's balance at a specific point in time by computing the difference from the
        outgoing balance and the sum of the incoming and network balances.
        :return: Token value of the display balance.
        :rtype: float
        """
        display = (self.network_balance + self.incoming_balance) - self.outgoing_balance
        return from_wei(decimals=self.decimals, value=display)

    def spendable_balance(self, chain_str: str, token_symbol: str):
        """This function calculates an account's spendable balance at a given point in time by computing the difference
        of outgoing balance from the network balance.
        :return: Token value of the spendable balance.
        :rtype: float
        """
        spendable = self.network_balance - self.outgoing_balance
        return from_wei(decimals=self.decimals, value=spendable)


def get_adjusted_balance(balance: int, chain_str: str, timestamp: int, token_symbol: str):
    """
    > Given a balance, chain, timestamp, and token symbol, return the adjusted balance

    :param balance: the amount of tokens you want to check the adjusted balance for
    :type balance: int
    :param chain_str: the chain you want to get the adjusted balance for
    :type chain_str: str
    :param timestamp: the timestamp of the block you want to get the adjusted balance for
    :type timestamp: int
    :param token_symbol: The symbol of the token you want to get the adjusted balance for
    :type token_symbol: str
    :return: The adjusted balance is being returned.
    """
    logg.debug(f'retrieving adjusted balance on chain: {chain_str} for balance: {balance}')
    demurrage_api = DemurrageApi(chain_str=chain_str)
    return demurrage_api.get_adjusted_balance(token_symbol, balance, timestamp).get()


def get_cached_balances(identifier: Union[list, bytes]):
    """
    :param identifier: An identifier needed to create a unique pointer to a balances resource.
    :type identifier: bytes | list
    :return:
    :rtype:
    """
    key = cache_data_key(identifier=identifier, salt=MetadataPointer.BALANCES)
    return get_cached_data(key=key)


def get_cached_display_balance(decimals: int, identifier: Union[list, bytes]) -> float:
    """This function attempts to retrieve balance data from the redis cache.
    :param decimals:
    :type decimals: int
    :param identifier: A list containing bytes representation of an address and an encoded token symbol
    :raises CachedDataNotFoundError: No cached balance data could be found.
    :return: Operational balance of an account.
    :rtype: float
    """

    if not (cached_balances := get_cached_balances(identifier=identifier)):
        raise CachedDataNotFoundError('No cached display balance.')
    balances = BalancesHandler(balances=json.loads(cached_balances), decimals=decimals)
    return balances.display_balance()


def get_cached_adjusted_balance(identifier: Union[list, bytes]):
    """
    It gets the cached adjusted balance for a given identifier

    :param identifier: The identifier of the account whose balance you want to retrieve
    :type identifier: Union[list, bytes]
    :return: The adjusted balance of the account.
    """
    key = cache_data_key(identifier, MetadataPointer.BALANCES_ADJUSTED)
    return get_cached_data(key)


def get_account_tokens_balance(blockchain_address: str, chain_str: str, queue: str, token_symbols_list: list):
    """
    > This function will get the balance of the specified token for the specified address and put the result in the
    specified queue

    :param blockchain_address: The address of the account you want to get the balance of
    :type blockchain_address: str
    :param chain_str: The blockchain you want to query
    :type chain_str: str
    :param queue: The name of the queue to which the response will be sent
    :type queue: str
    :param token_symbols_list: list of token symbols to get balances for
    :type token_symbols_list: list
    """
    for token_symbol in token_symbols_list:
        get_balances(address=blockchain_address,
                     chain_str=chain_str,
                     token_symbol=token_symbol,
                     asynchronous=True,
                     callback_param=f'{blockchain_address},{token_symbol}',
                     callback_queue=queue)
