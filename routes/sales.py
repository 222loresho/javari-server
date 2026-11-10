import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.sale import Sale, SaleItem
from models.order import kenya_time
from line_items import build_lines
from tenant import current_user, scoped

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
    user = current_user()
    if user is None:
        return jsonify({"error": "Account is inactive"}), 401
    data  = request.get_json(silent=True) or {}
    lines, total, err = build_lines(user, data.get("items"))
    if err:
        return jsonify({"error": err}), 400

    try:
        paid = float(data.get("amount_paid", total))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount paid"}), 400
    if not math.isfinite(paid) or paid < 0:
        return jsonify({"error": "Invalid amount paid"}), 400

    change = round(max(0, paid - total), 2)
    sale = Sale(
        cashier_id     = user.id,
        cashier_name   = user.name,
        total          = total,
        amount_paid    = paid,
        change_due     = change,
        payment_method = str(data.get("payment_method") or "cash")[:20],
        created_at     = kenya_time(),
        market_id      = user.market_id,
    )
    db.session.add(sale)
    db.session.flush()
    for line in lines:
        db.session.add(SaleItem(
            sale_id      = sale.id,
            product_id   = line["product"].id,
            product_name = line["name"],
            quantity     = line["quantity"],
            price        = line["price"],
            subtotal     = line["subtotal"]
        ))
        line["product"].stock = max(0, line["product"].stock - line["quantity"])
    db.session.commit()
    return jsonify({"message": "Sale created", "change_due": change, "total": total}), 201
