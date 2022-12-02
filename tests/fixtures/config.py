# standard imports
import logging
import os

# third party imports
import i18n
import pytest
from chainlib.chain import ChainSpec
from confini import Config

# local imports
from cic_ussd.account.chain import Chain
from cic_ussd.account.guardianship import Guardianship
from cic_ussd.files.local_files import create_local_file_data_stores, json_file_parser
from cic_ussd.menu.ussd_menu import UssdMenu
from cic_ussd.phone_number import E164Format, Support
from cic_ussd.state_machine import UssdStateMachine
from cic_ussd.state_machine.logic.manager import States
from cic_ussd.translation import generate_locale_files, Languages
from cic_ussd.validator import validate_presence
from cic_ussd.time import TimezoneHandler

logg = logging.getLogger(__name__)

fixtures_dir = os.path.dirname(__file__)
root_directory = os.path.dirname(os.path.dirname(fixtures_dir))


@pytest.fixture(scope='session')
def alembic_config():
    migrations_directory = os.path.join(root_directory, 'cic_ussd', 'db', 'migrations', 'default')
    file = os.path.join(migrations_directory, 'alembic.ini')
    return {
        'file': file,
        'script_location': migrations_directory
    }


@pytest.fixture(scope='function')
def init_state_machine(load_config):
    UssdStateMachine.states = json_file_parser(filepath=load_config.get('MACHINE_STATES'))
    UssdStateMachine.transitions = json_file_parser(filepath=load_config.get('MACHINE_TRANSITIONS'))


@pytest.fixture(scope='function')
def load_languages(init_cache, load_config):
    validate_presence(load_config.get('LANGUAGES_FILE'))
    Languages.load_languages_dict(load_config.get('LANGUAGES_FILE'))
    languages = Languages()
    languages.cache_system_languages()


@pytest.fixture(scope='function')
def load_chain_spec(load_config):
    chain_spec = ChainSpec.from_chain_str(load_config.get('CHAIN_SPEC'))
    Chain.spec = chain_spec


@pytest.fixture(scope='session')
def load_config():
    config_directory = os.path.join(root_directory, 'config/test')
    config = Config(default_dir=config_directory)
    config.process()
    logg.debug('config loaded\n{}'.format(config))
    return config


@pytest.fixture(scope='function')
def load_e164_region(load_config):
    E164Format.region = load_config.get('E164_REGION')


@pytest.fixture(scope='session', autouse=True)
def load_non_resumable_states(load_config):
    States.load_non_resumable_states(load_config.get('MACHINE_NON_RESUMABLE_STATES'))


@pytest.fixture(scope='session')
def load_support_phone(load_config):
    Support.phone_number = load_config.get('OFFICE_SUPPORT_PHONE')


@pytest.fixture
def load_ussd_menu(load_config):
    ussd_menu_db = create_local_file_data_stores(file_location=load_config.get('USSD_MENU_FILE'), table_name="ussd_menu")
    UssdMenu.ussd_menu_db = ussd_menu_db


@pytest.fixture(scope='function')
def setup_guardianship(load_config):
    guardians_file = os.path.join(root_directory, load_config.get('SYSTEM_GUARDIANS_FILE'))
    validate_presence(guardians_file)
    Guardianship.load_system_guardians(guardians_file)


@pytest.fixture(scope="session")
def set_locale_files(load_config, tmpdir_factory):
    tmpdir = tmpdir_factory.mktemp("var")
    tmpdir_path = str(tmpdir)
    validate_presence(tmpdir_path)
    import cic_translations
    package_path = cic_translations.__path__
    schema_files = os.path.join(package_path[0], load_config.get("SCHEMA_FILE_PATH"))
    generate_locale_files(locale_dir=tmpdir_path,
                          schema_file_path=schema_files,
                          translation_builder_path=load_config.get('LOCALE_FILE_BUILDERS'))
    i18n.load_path.append(tmpdir_path)
    i18n.set('fallback', load_config.get('LOCALE_FALLBACK'))


@pytest.fixture(scope='function')
def load_timezone(load_config):
    TimezoneHandler.timezone = load_config.get("TIME_ZONE")
