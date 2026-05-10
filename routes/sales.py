from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.sale import Sale, SaleItem
from models.product import Product
from models.user import User
from models.order import kenya_time

sales_bp = Blueprint("sales", __name__)

@sales_bp.route("/", methods=["GET"])
@jwt_required()
def get_sales():
    return jsonify([{
        "id":             s.id,
        "cashier_name":   s.cashier_name,
        "total":          float(s.total),
        "amount_paid":    float(s.amount_paid),
        "change_due":     float(s.change_due),
        "payment_method": s.payment_method,
        "created_at":     s.created_at.isoformat()
    } for s in Sale.query.order_by(Sale.created_at.desc()).all()])

@sales_bp.route("/", methods=["POST"])
@jwt_required()
def create_sale():
    identity = get_jwt_identity()
    user     = User.query.get(identity)
    data     = request.get_json()
    items    = data.get("items", [])
    total    = sum(i["subtotal"] for i in items)
    paid     = float(data.get("amount_paid", total))
    change   = max(0, paid - total)
    sale = Sale(
        cashier_id     = identity,
        cashier_name   = user.name,
        total          = total,
        amount_paid    = paid,
        change_due     = change,
        payment_method = data.get("payment_method", "cash"),
        created_at     = kenya_time()
    )
    db.session.add(sale)
    db.session.flush()
    for item in items:
        db.session.add(SaleItem(
            sale_id      = sale.id,
            product_id   = item["product_id"],
            product_name = item["product_name"],
            quantity     = item["quantity"],
            price        = item["price"],
            subtotal     = item["subtotal"]
        ))
        p = Product.query.get(item["product_id"])
        if p: p.stock = max(0, p.stock - item["quantity"])
    db.session.commit()
    return jsonify({"message": "Sale created", "change_due": change}), 201