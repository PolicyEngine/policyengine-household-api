from policyengine_household_api.api import db

class Visit(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  client_id = db.Column(db.String(255), nullable=False)
  date = db.Column(db.Date)
  time = db.Column(db.Time)
  api_version = db.Column(db.String(32))
  endpoint = db.Column(db.String(64))
  method = db.Column(db.String(32))
  content_length_bytes = db.Column(db.Integer)
  duration_ms = db.Column(db.Integer)