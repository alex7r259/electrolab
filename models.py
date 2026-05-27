from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Protocol(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    protocol_number = db.Column(db.String(100))
    protocol_name = db.Column(db.String(500))

    object_name = db.Column(db.String(1000))

    test_date = db.Column(db.Date)

    engineers = db.Column(db.String(500))

    file_path = db.Column(db.String(2000), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)