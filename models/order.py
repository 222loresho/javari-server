from extensions import db
from datetime import datetime, timezone, timedelta

KENYA_TZ = timezone(timedelta(hours=3))

def kenya_time():
    return datetime.now(KENYA_TZ).replace(tzinfo=None)

class Order(db.Model):
    __tablename__ = "orders"
    id              = db.Column(db.Integer,       primary_key=True)
    order_number    = db.Column(db.String(20))
    table_name      = db.Column(db.String(50))
    cashier_id      = db.Column(db.Integer,       db.ForeignKey("users.id"))
    cashier_name    = db.Column(db.String(100))
    waiter_name     = db.Column(db.String(100))
    status          = db.Column(db.String(20),    default="pending")
    total           = db.Column(db.Numeric(10,2))
    payment_method  = db.Column(db.String(50))
    payment_details = db.Column(db.JSON)
    submitted_at    = db.Column(db.DateTime)
    confirmed_at    = db.Column(db.DateTime)
    confirmed_by    = db.Column(db.String(100))
    rejection_note  = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=kenya_time)
    items           = db.relationship("OrderItem", backref="order", lazy=True)

class OrderItem(db.Model):
    __tablename__ = "order_items"
    id           = db.Column(db.Integer,       primary_key=True)
    order_id     = db.Column(db.Integer,       db.ForeignKey("orders.id"))
    product_id   = db.Column(db.Integer,       db.ForeignKey("products.id"))
    product_name = db.Column(db.String(100))
    quantity     = db.Column(db.Integer)
    price        = db.Column(db.Numeric(10,2))
    subtotal     = db.Column(db.Numeric(10,2))