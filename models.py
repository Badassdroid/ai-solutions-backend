from db import db
from datetime import datetime

class Inquiry(db.Model):
    __tablename__ = 'inquiries'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    company = db.Column(db.String(100))
    country = db.Column(db.String(100))
    job_title = db.Column(db.String(100))
    job_details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
