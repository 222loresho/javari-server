from extensions import db
from datetime import datetime, timezone, timedelta

KENYA_TZ = timezone(timedelta(hours=3))
def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)

class Market(db.Model):
    __tablename__ = "markets"
    id            = db.Column(db.Integer,       primary_key=True)
    name          = db.Column(db.String(100),   nullable=False)
    location      = db.Column(db.String(200))
    contact_name  = db.Column(db.String(100))
    contact_email = db.Column(db.String(100))
    contact_phone = db.Column(db.String(30))
    plan          = db.Column(db.String(20),    default="trial")
    monthly_fee   = db.Column(db.Numeric(10,2), default=0)
    currency      = db.Column(db.String(10),    default="KES")
    status        = db.Column(db.String(20),    default="trial")
    api_url       = db.Column(db.String(200))
    notes         = db.Column(db.Text)
    created_at    = db.Column(db.DateTime,      default=kenya_time)
    last_payment  = db.Column(db.DateTime)
    next_payment  = db.Column(db.DateTime)