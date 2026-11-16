from datetime import datetime, timezone, timedelta

from extensions import db

KENYA_TZ = timezone(timedelta(hours=3))


def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)


class WebhookEvent(db.Model):
    __tablename__ = "webhook_events"
    id          = db.Column(db.Integer, primary_key=True)
    source      = db.Column(db.String(40), default="generic", index=True)
    event_type  = db.Column(db.String(80))
    delivery    = db.Column(db.String(64))
    payload     = db.Column(db.JSON)
    ip          = db.Column(db.String(64))
    received_at = db.Column(db.DateTime, default=kenya_time, index=True)
