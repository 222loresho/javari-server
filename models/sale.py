from extensions import db
from datetime import datetime, timezone, timedelta

KENYA_TZ = timezone(timedelta(hours=3))

def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)

class Sale(db.Model):
    __tablename__ = "sales"
    id             = db.Column(db.Integer,       primary_key=True)
    cashier_id     = db.Column(db.Integer,       db.ForeignKey("users.id"))
    cashier_name   = db.Column(db.String(100))
    total          = db.Column(db.Numeric(10,2))
    amount_paid    = db.Column(db.Numeric(10,2))
    change_due     = db.Column(db.Numeric(10,2))
    payment_method = db.Column(db.String(20),    default="cash")
    created_at     = db.Column(db.DateTime,      default=kenya_time)
    items          = db.relationship("SaleItem",  backref="sale", lazy=True)

class SaleItem(db.Model):
    __tablename__ = "sale_items"
    id           = db.Column(db.Integer,       primary_key=True)
    sale_id      = db.Column(db.Integer,       db.ForeignKey("sales.id"))
    product_id   = db.Column(db.Integer,       db.ForeignKey("products.id"))
    product_name = db.Column(db.String(100))
    quantity     = db.Column(db.Integer)
    price        = db.Column(db.Numeric(10,2))
    subtotal     = db.Column(db.Numeric(10,2))