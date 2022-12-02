"""This module handles requests originating from the ussd service provider.
"""

# standard imports
import json
import logging

# external imports
import celery
import i18n
import redis
from chainlib.chain import ChainSpec
from cic_types.condiments import MetadataPointer
from cic_types.ext.metadata import Metadata
from cic_types.ext.metadata.signer import Signer
from confini import Config

# local imports
from cic_ussd.account.chain import Chain
from cic_ussd.account.guardianship import Guardianship
from cic_ussd.account.tokens import query_default_token
from cic_ussd.cache import cache_data, cache_data_key, Cache
from cic_ussd.db import dsn_from_config
from cic_ussd.db.models.base import SessionBase
from cic_ussd.error import InitializationError
from cic_ussd.files.local_files import create_local_file_data_stores, json_file_parser
from cic_ussd.http.requests import get_request_endpoint, get_request_method
from cic_ussd.http.responses import with_content_headers
from cic_ussd.menu.ussd_menu import UssdMenu
from cic_ussd.phone_number import Support, E164Format, OfficeSender
from cic_ussd.processor.ussd import handle_menu_operations
from cic_ussd.runnable.server_base import exportable_parser, logg
from cic_ussd.session.ussd_session import UssdSession as InMemoryUssdSession
from cic_ussd.state_machine import UssdStateMachine
from cic_ussd.state_machine.logic.manager import States
from cic_ussd.time import TimezoneHandler
from cic_ussd.translation import generate_locale_files, Languages, translation_for
from cic_ussd.validator import validate_presence
from cic_ussd.worker import Worker

args = exportable_parser.parse_args()

# define log levels
if args.vv:
    logging.getLogger().setLevel(logging.DEBUG)
elif args.v:
    logging.getLogger().setLevel(logging.INFO)

# parse config
config = Config(args.c, env_prefix=args.env_prefix)
config.process()
config.censor('PASSWORD', 'DATABASE')
logg.debug(f'config loaded from {args.c}:\n{config}')

# set up db
data_source_name = dsn_from_config(config)
SessionBase.connect(data_source_name,
                    pool_size=int(config.get('DATABASE_POOL_SIZE')),
                    debug=config.true('DATABASE_DEBUG'))

# create in-memory databases
ussd_menu_db = create_local_file_data_stores(file_location=config.get('USSD_MENU_FILE'),
                                             table_name='ussd_menu')
UssdMenu.ussd_menu_db = ussd_menu_db

# define universal redis cache access
Cache.store = redis.StrictRedis(host=config.get('REDIS_HOST'),
                                port=config.get('REDIS_PORT'),
                                password=config.get('REDIS_PASSWORD'),
                                db=config.get('REDIS_DATABASE'),
                                decode_responses=True)
InMemoryUssdSession.store = Cache.store

# define metadata URL
Metadata.base_url = config.get('CIC_META_URL')

# define signer values
export_dir = config.get('PGP_EXPORT_DIR')
if export_dir:
    validate_presence(path=export_dir)
Signer.gpg_path = export_dir
Signer.gpg_passphrase = config.get('PGP_PASSPHRASE')
key_file_path = f"{config.get('PGP_KEYS_PATH')}{config.get('PGP_PRIVATE_KEYS')}"
if key_file_path:
    validate_presence(path=key_file_path)
Signer.key_file_path = key_file_path

# initialize celery app
celery.Celery(backend=config.get('CELERY_RESULT_URL'), broker=config.get('CELERY_BROKER_URL'))

# load states and transitions data
states = json_file_parser(filepath=config.get('MACHINE_STATES'))
transitions = json_file_parser(filepath=config.get('MACHINE_TRANSITIONS'))

# make non-resumable states accessible globally
States.load_non_resumable_states(config.get("MACHINE_NON_RESUMABLE_STATES"))

chain_spec = ChainSpec.from_chain_str(config.get('CHAIN_SPEC'))

Chain.spec = chain_spec
Chain.rpc_provider = config.get('RPC_PROVIDER')
UssdStateMachine.states = states
UssdStateMachine.transitions = transitions

# retrieve default token data
chain_str = Chain.spec.__str__()
if not (default_token_data := query_default_token(chain_str)):
    raise InitializationError(f'Default token data for: {chain_str} not found.')

cache_key = cache_data_key(chain_str.encode('utf-8'), MetadataPointer.TOKEN_DEFAULT)
cache_data(key=cache_key, data=json.dumps(default_token_data))
valid_service_codes = config.get('USSD_SERVICE_CODE').split(",")

E164Format.region = config.get('E164_REGION')
Support.phone_number = config.get('OFFICE_SUPPORT_PHONE')

validate_presence(config.get('SYSTEM_GUARDIANS_FILE'))
Guardianship.load_system_guardians(config.get('SYSTEM_GUARDIANS_FILE'))

generate_locale_files(locale_dir=config.get('LOCALE_PATH'),
                      schema_file_path=config.get('SCHEMA_FILE_PATH'),
                      translation_builder_path=config.get('LOCALE_FILE_BUILDERS'))

# set up translations
i18n.load_path.append(config.get('LOCALE_PATH'))
i18n.set('fallback', config.get('LOCALE_FALLBACK'))

validate_presence(config.get('LANGUAGES_FILE'))
Languages.load_languages_dict(config.get('LANGUAGES_FILE'))
languages = Languages()
languages.cache_system_languages()

TimezoneHandler.timezone = config.get("TIME_ZONE")
OfficeSender.tag = config.get('OFFICE_SENDER_TAG')
Worker.queue_name = config.get('CELERY_QUEUE_NAME')
logg.debug(f"Celery queue name is: {Worker.queue_name}")


def application(env, start_response):
    """Loads python code for application to be accessible over web server
    :param env: Object containing server and request information
    :type env: dict
    :param start_response: Callable to define responses.
    :type start_response: any
    :return: a list containing a bytes representation of the response object
    :rtype: list
    """
    # define headers
    errors_headers = [('Content-Type', 'text/plain'), ('Content-Length', '0')]
    headers = [('Content-Type', 'application/json')]

    # create session for the life-time of http request
    session = SessionBase.create_session()

    if get_request_endpoint(env) == '/health-check':
        session.close()
        start_response('200 OK', headers)
        return [b'healthy']

    elif get_request_method(env=env) == 'POST' and get_request_endpoint(env=env) == '/':

        if env.get("CONTENT_TYPE") != 'application/json':
            return system_error(session, start_response, '400 Malformed', errors_headers)

        post_data = json.load(env.get('wsgi.input'))
        logg.debug(f"Received request with data of the form: {post_data}")
        service_code = post_data.get("ussd_code")
        phone_number = post_data.get("msisdn")
        external_session_id = cache_data_key(phone_number.encode("utf-8"), MetadataPointer.NONE)
        user_input = post_data.get("ussd_response")

        if service_code not in valid_service_codes:
            response = translation_for(
                'ussd.invalid_service_code',
                i18n.config.get('fallback'),
                valid_service_code=valid_service_codes[0]
            )
            response_bytes, headers = with_content_headers(headers, response)
            start_response('200 OK', headers)
            return [response_bytes]

        logg.debug('session {} started for {}'.format(external_session_id, phone_number))
        logg.debug(f"Attempting to handle request for {phone_number}")

        try:
            response = handle_menu_operations(external_session_id,
                                              phone_number,
                                              Worker.queue_name,
                                              service_code,
                                              session,
                                              user_input)
            response_bytes, headers = with_content_headers(headers, response)
            start_response('200 OK,', headers)
            session.commit()
            session.close()
            return [response_bytes]
        except Exception as e:
            logg.error(f"Error occurred while handling request: {e}")
            session.rollback()
            return system_error(session, start_response, '500 Internal Server Error', errors_headers)

    else:
        logg.error(f'invalid query {env}')
        for r in env:
            logg.debug(f'{r}: {env}')
        return system_error(session, start_response, '405 Play by the rules', errors_headers)


def system_error(session, start_response, arg2, errors_headers):
    session.close()
    start_response(arg2, errors_headers)
    return []
