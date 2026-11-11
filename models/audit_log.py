from datetime import datetime, timezone, timedelta

from extensions import db

KENYA_TZ = timezone(timedelta(hours=3))


def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id         = db.Column(db.Integer, primary_key=True)
    actor_id   = db.Column(db.Integer)
    actor_name = db.Column(db.String(100))
    action     = db.Column(db.String(60), index=True)
    detail     = db.Column(db.String(500))
    ip         = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=kenya_time, index=True)
