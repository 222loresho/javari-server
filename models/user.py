from extensions import db

class User(db.Model):
    __tablename__ = "users"
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50),  unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role     = db.Column(db.String(20),  default="cashier")
    active   = db.Column(db.Boolean,     default=True)
    pin      = db.Column(db.String(10),  default="1234")