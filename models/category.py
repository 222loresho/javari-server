from extensions import db

class Category(db.Model):
    __tablename__ = "categories"
    id   = db.Column(db.Integer,     primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    market_id = db.Column(db.Integer, db.ForeignKey("markets.id"), nullable=True)