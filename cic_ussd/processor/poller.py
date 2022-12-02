# standard imports
import logging
import time
from queue import Queue
from typing import Callable, Dict, Optional, Tuple, Union

# external imports
from cic_types.condiments import MetadataPointer

# local imports
from cic_ussd.cache import cache_data_key, get_cached_data
from cic_ussd.error import MaxRetryReached


logg = logging.getLogger()


# adapted from https://github.com/justiniso/polling/blob/master/polling.py
# opted not to use the package to reduce dependency
def poller(args: Optional[Tuple],
           interval: int,
           kwargs: Optional[Dict],
           max_retry: int,
           target: Callable[..., Union[Dict, str]]):
    """"""
    collected_values: list = []
    expected_value = None
    tries = 0

    while True:
        if tries >= max_retry:
            raise MaxRetryReached(collected_values, expected_value)
        try:
            if args:
                value = target(*args)
            elif kwargs:
                value = target(**kwargs)
            else:
                value = target()
            expected_value = value
        except () as error:
            expected_value = error
        else:
            if bool(value) or value == {}:
                logg.debug(f'Resource: {expected_value} now available.')
                break
        collected_values.append(expected_value)
        logg.debug(f'Collected values are: {collected_values}')
        tries += 1
        time.sleep(interval)


def wait_for_cache(identifier: Union[list, bytes],
                   resource_name: str,
                   salt: MetadataPointer,
                   interval: int = 3,
                   max_retry: int = 15):
    """
    > Poll the cache for a resource, and return the resource when it's found

    :param identifier: The identifier of the resource you're waiting for
    :type identifier: Union[list, bytes]
    :param resource_name: The name of the resource you're waiting for
    :type resource_name: str
    :param salt: MetadataPointer
    :type salt: MetadataPointer
    :param interval: The number of seconds to wait between each poll, defaults to 3
    :type interval: int (optional)
    :param max_retry: The number of times to poll the cache, defaults to 15
    :type max_retry: int (optional)
    """
    key: str = cache_data_key(identifier=identifier, salt=salt)
    logg.debug(f'Polling for resource: {resource_name} at: {key} every: {interval} second(s) for {max_retry} seconds.')
    poller(args=(key,), interval=interval, kwargs=None, max_retry=max_retry, target=get_cached_data)


def wait_for_session_data(resource_name: str, session_data_key: str, ussd_session: dict, interval: int = 1, max_retry: int = 15):
    """
    It polls for the data element in the session dictionary and then polls for the session data element in the data
    dictionary

    :param resource_name: The name of the resource you're waiting for
    :type resource_name: str
    :param session_data_key: The key of the session data element you want to wait for
    :type session_data_key: str
    :param ussd_session: The session object returned by the `ussd_session` function
    :type ussd_session: dict
    :param interval: The time in seconds to wait before checking for the data element, defaults to 1
    :type interval: int (optional)
    :param max_retry: The maximum number of times to retry the function, defaults to 15
    :type max_retry: int (optional)
    """
    # poll for data element first
    logg.debug(f'Data poller with max retry at: {max_retry}. Checking for every: {interval} seconds.')
    poller(args=('data',), interval=interval, kwargs=None, max_retry=max_retry, target=ussd_session.get)

    # poll for session data element
    get_session_data = ussd_session.get('data').get
    logg.debug(f'Session data poller for: {resource_name} with max retry at: {max_retry}. Checking for every: {interval} seconds.')
    poller(args=(session_data_key,), interval=interval, kwargs=None, max_retry=max_retry, target=get_session_data)

