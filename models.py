from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Protocol(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    protocol_number = db.Column(db.String(100))
    protocol_name = db.Column(db.String(500))

    object_name = db.Column(db.String(1000))

    test_date = db.Column(db.Date)

    engineers = db.Column(db.String(500))

    file_path = db.Column(db.String(2000), unique=True)
    last_modified = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Instrument(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    device_name = db.Column(db.String(255), nullable=False)
    test_types = db.Column(db.String(255), default="")
    serial_number = db.Column(db.String(255), default="")

    last_verification = db.Column(db.Date)
    next_verification = db.Column(db.Date)

    certificate_number = db.Column(db.String(255), default="")
    passport_info = db.Column(db.String(255), default="")
    note = db.Column(db.String(1000), default="")

    in_verification = db.Column(db.Boolean, default=False)
    written_off = db.Column(db.Boolean, default=False)

    fgis_data = db.Column(db.Text, default="")
    fgis_sync_date = db.Column(db.DateTime)


class ActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    action = db.Column(db.String(50), nullable=False)
    device_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000), nullable=False)

    username = db.Column(db.String(255), default="system")
    ip_address = db.Column(db.String(255), default="unknown")

    created_at = db.Column(db.DateTime, default=datetime.now)
