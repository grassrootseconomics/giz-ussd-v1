# standard imports
import logging

# third-party imports
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm.session import Session

# local imports
from cic_ussd.db.models.base import SessionBase

logg = logging.getLogger(__name__)


class TxMeta(SessionBase):
    __tablename__ = 'tx_meta'

    tx_reason = Column(String)
    tx_from = Column(String)
    tx_to = Column(String)
    tx_amount = Column(Integer)
