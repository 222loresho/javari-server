from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.sale import Sale, SaleItem
from models.product import Product
from models.order import kenya_time
from tenant import current_user, scoped, in_venue

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
    } for s in scoped(Sale).order_by(Sale.created_at.desc()).all()])

@sales_bp.route("/", methods=["POST"])
@jwt_required()
def create_sale():
    user  = current_user()
    data  = request.get_json()
    items = data.get("items", [])
    products = {}
    for item in items:
        p = Product.query.get(item["product_id"])
        if not p or not in_venue(p, user):
            return jsonify({"error": f"Unknown product: {item.get('product_name', '')}"}), 400
        products[item["product_id"]] = p

    total  = sum(i["subtotal"] for i in items)
    paid   = float(data.get("amount_paid", total))
    change = max(0, paid - total)
    sale = Sale(
        cashier_id     = user.id,
        cashier_name   = user.name,
        total          = total,
        amount_paid    = paid,
        change_due     = change,
        payment_method = data.get("payment_method", "cash"),
        created_at     = kenya_time(),
        market_id      = user.market_id,
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
        products[item["product_id"]].stock = max(0, products[item["product_id"]].stock - item["quantity"])
    db.session.commit()
    return jsonify({"message": "Sale created", "change_due": change}), 201
