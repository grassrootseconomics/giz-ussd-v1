# standard import
from enum import IntEnum, Enum


class AccountStatus(IntEnum):
    PENDING = 1
    ACTIVE = 2
    LOCKED = 3
    RESET = 4


class OrganizationTag(Enum):
    GRASSROOTS = 'Grassroots Economics'
    GIZ = 'GIZ'
