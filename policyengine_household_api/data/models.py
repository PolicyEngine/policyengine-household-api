from policyengine_household_api.api import db
from sqlalchemy import Integer, String, Date, Time
from sqlalchemy.orm import mapped_column

class Visits(db.Model):
  id = mapped_column(Integer, primary_key=True)
  client_id = mapped_column(String(255), nullable=False)
  date = mapped_column(Date)
  time = mapped_column(Time)
  api_version = mapped_column(String(32))
  endpoint = mapped_column(String(64))
  method = mapped_column(String(32))
  content_length_bytes = mapped_column(Integer)
  duration_ms = mapped_column(Integer)