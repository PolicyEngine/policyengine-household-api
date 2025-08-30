# from policyengine_household_api.api import analytics_db
from policyengine_household_api.data.analytics_setup import db
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import mapped_column


# class Visit(analytics_db.Model):
class Visit(db.Model):
    # Note that the model represents one visit,
    # while the table name is plural
    __tablename__ = "visits"
    id = mapped_column(Integer, primary_key=True)
    client_id = mapped_column(String(255), nullable=False)
    datetime = mapped_column(DateTime)
    api_version = mapped_column(String(32))
    endpoint = mapped_column(String(64))
    method = mapped_column(String(32))
    content_length_bytes = mapped_column(Integer)
