# standard imports
import logging

# external imports
from sqlalchemy import Column, String, Integer, Boolean


# local imports
from cic_ussd.db.models.base import SessionBase

logg = logging.getLogger(__name__)


class SurveyResponse(SessionBase):
    __tablename__ = 'survey_response'

    phone_number = Column(String, index=True)
    village = Column(String)
    gender = Column(String)
    economic_activity = Column(String)
    monthly_expenditure = Column(String)
    expenditure_band = Column(String)
