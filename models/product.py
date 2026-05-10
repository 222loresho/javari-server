from extensions import db

class Product(db.Model):
    __tablename__ = "products"
    id          = db.Column(db.Integer,       primary_key=True)
    name        = db.Column(db.String(100),   nullable=False)
    price       = db.Column(db.Numeric(10,2), nullable=False)
    stock       = db.Column(db.Integer,       default=0)
    category_id = db.Column(db.Integer,       db.ForeignKey("categories.id"), nullable=True)