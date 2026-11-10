from extensions import db

class User(db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    username   = db.Column(db.String(50),  nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20),  default="cashier")
    active     = db.Column(db.Boolean,     default=True)
    pin        = db.Column(db.String(10),  default="1234")
    market_id  = db.Column(db.Integer, db.ForeignKey("markets.id"), nullable=True)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
