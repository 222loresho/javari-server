from datetime import datetime, timezone, timedelta

from extensions import db

KENYA_TZ = timezone(timedelta(hours=3))


def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)


class LoginEvent(db.Model):
    __tablename__ = "login_events"
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(50), index=True)
    ip         = db.Column(db.String(64), index=True)
    succeeded  = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=kenya_time, index=True)
