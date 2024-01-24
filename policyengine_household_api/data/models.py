from api import db

class Visit(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  client_id = db.Column(db.String, nullable=False)
  date = db.Column(db.Date)
  time = db.Column(db.Time)
  endpoint = db.Column(db.String)
  method = db.Column(db.String)
  content_length_bytes = db.Column(db.Integer)
  duration_ms = db.Column(db.Integer)