from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import jwt_required
from extensions import db
from models.order import Order, OrderItem, kenya_time
from models.sale import Sale, SaleItem
from models.product import Product
from tenant import current_user, scoped, in_venue

orders_bp = Blueprint("orders", __name__)

def load_order(oid):
    order = Order.query.get_or_404(oid)
    if not in_venue(order):
        abort(404)
    return order

def items_in_venue(user, items):
    for item in items:
        product = Product.query.get(item["product_id"])
        if not product or not in_venue(product, user):
            return False
    return True

@orders_bp.route("/", methods=["GET"])
@jwt_required()
def get_orders():
    return jsonify([serialize(o) for o in scoped(Order).filter_by(status="pending").order_by(Order.created_at.desc()).all()])

@orders_bp.route("/submitted", methods=["GET"])
@jwt_required()
def get_submitted():
    return jsonify([serialize(o) for o in scoped(Order).filter_by(status="submitted").order_by(Order.submitted_at.desc()).all()])

@orders_bp.route("/confirmed", methods=["GET"])
@jwt_required()
def get_confirmed():
    return jsonify([serialize(o) for o in scoped(Order).filter_by(status="confirmed").order_by(Order.confirmed_at.desc()).limit(50).all()])

@orders_bp.route("/completed", methods=["GET"])
@jwt_required()
def get_completed():
    return jsonify([serialize(o) for o in scoped(Order).filter_by(status="completed").order_by(Order.created_at.desc()).limit(100).all()])

@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    data = request.json
    user = current_user()
    if not items_in_venue(user, data["items"]):
        return jsonify({"error": "Unknown product in cart"}), 400
    last     = Order.query.order_by(Order.id.desc()).first()
    next_num = (last.id + 1) if last else 1
    order    = Order(
        table_name   = data["table_name"],
        cashier_id   = user.id,
        cashier_name = user.name,
        waiter_name  = data.get("waiter_name", user.name),
        status       = "pending",
        total        = data["total"],
        order_number = f"#{next_num:04d}",
        created_at   = kenya_time(),
        market_id    = user.market_id,
    )
    db.session.add(order)
    db.session.flush()
    for item in data["items"]:
        db.session.add(OrderItem(
            order_id     = order.id,
            product_id   = item["product_id"],
            product_name = item["product_name"],
            quantity     = item["quantity"],
            price        = item["price"],
            subtotal     = item["subtotal"]
        ))
    db.session.commit()
    return jsonify({"message": "Order created", "id": order.id, "order_number": order.order_number}), 201

@orders_bp.route("/<int:oid>", methods=["PUT"])
@jwt_required()
def update_order(oid):
    order = load_order(oid)
    data  = request.json
    if not items_in_venue(current_user(), data["items"]):
        return jsonify({"error": "Unknown product in cart"}), 400
    order.total = data["total"]
    OrderItem.query.filter_by(order_id=oid).delete()
    for item in data["items"]:
        db.session.add(OrderItem(
            order_id     = oid,
            product_id   = item["product_id"],
            product_name = item["product_name"],
            quantity     = item["quantity"],
            price        = item["price"],
            subtotal     = item["subtotal"]
        ))
    db.session.commit()
    return jsonify({"message": "Order updated"})

@orders_bp.route("/<int:oid>/submit", methods=["POST"])
@jwt_required()
def submit_order(oid):
    order = load_order(oid)
    data  = request.json
    order.status          = "submitted"
    order.payment_method  = data.get("payment_method", "cash")
    order.payment_details = data.get("splits", [])
    order.submitted_at    = kenya_time()
    db.session.commit()
    return jsonify({"message": "Order submitted for confirmation"})

@orders_bp.route("/<int:oid>/confirm", methods=["POST"])
@jwt_required()
def confirm_order(oid):
    user  = current_user()
    order = load_order(oid)
    total = float(order.total)
    sale = Sale(
        cashier_id     = user.id,
        cashier_name   = user.name,
        total          = total,
        amount_paid    = total,
        change_due     = 0,
        payment_method = order.payment_method or "cash",
        created_at     = kenya_time(),
        market_id      = order.market_id,
    )
    db.session.add(sale)
    db.session.flush()
    for item in order.items:
        db.session.add(SaleItem(
            sale_id      = sale.id,
            product_id   = item.product_id,
            product_name = item.product_name,
            quantity     = item.quantity,
            price        = item.price,
            subtotal     = item.subtotal
        ))
        product = Product.query.get(item.product_id)
        if product and in_venue(product, user):
            product.stock = max(0, product.stock - item.quantity)
    order.status       = "confirmed"
    order.confirmed_at = kenya_time()
    order.confirmed_by = user.name
    db.session.commit()
    return jsonify({"message": "Order confirmed", "change_due": 0})

@orders_bp.route("/<int:oid>/reject", methods=["POST"])
@jwt_required()
def reject_order(oid):
    order = load_order(oid)
    data  = request.json
    order.status          = "pending"
    order.rejection_note  = data.get("note", "Payment rejected by cashier")
    order.payment_method  = None
    order.payment_details = None
    order.submitted_at    = None
    db.session.commit()
    return jsonify({"message": "Order rejected"})

@orders_bp.route("/<int:oid>", methods=["DELETE"])
@jwt_required()
def delete_order(oid):
    order = load_order(oid)
    OrderItem.query.filter_by(order_id=oid).delete()
    db.session.delete(order)
    db.session.commit()
    return jsonify({"message": "Order cancelled"})

def serialize(o):
    return {
        "id":             o.id,
        "order_number":   o.order_number,
        "table_name":     o.table_name,
        "waiter_name":    o.waiter_name,
        "cashier_name":   o.cashier_name,
        "status":         o.status,
        "total":          float(o.total),
        "payment_method": o.payment_method,
        "payment_details":o.payment_details,
        "rejection_note": o.rejection_note,
        "created_at":     o.created_at.isoformat()   if o.created_at   else None,
        "submitted_at":   o.submitted_at.isoformat()  if o.submitted_at else None,
        "confirmed_at":   o.confirmed_at.isoformat()  if o.confirmed_at else None,
        "confirmed_by":   o.confirmed_by,
        "items": [{
            "product_id":   i.product_id,
            "product_name": i.product_name,
            "quantity":     i.quantity,
            "price":        float(i.price),
            "subtotal":     float(i.subtotal)
        } for i in o.items]
    }
