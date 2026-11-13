from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import jwt_required
from extensions import db
from models.order import Order, OrderItem, kenya_time
from models.sale import Sale, SaleItem
from models.product import Product
from line_items import build_lines
from tenant import current_user, scoped, in_venue
from audit import log as audit_log

orders_bp = Blueprint("orders", __name__)

CASHIER_ROLES = ("admin", "manager", "cashier")


def load_order(oid):
    order = Order.query.get_or_404(oid)
    if not in_venue(order):
        abort(404)
    return order


def _require_staff():
    user = current_user()
    if user is None:
        return None, (jsonify({"error": "Account is inactive"}), 401)
    return user, None


def _require_cashier():
    user, err = _require_staff()
    if err:
        return None, err
    if user.role not in CASHIER_ROLES and user.role != "super_admin":
        return None, (jsonify({"error": "Only a cashier, manager or admin can do this"}), 403)
    return user, None


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
    return jsonify([serialize(o) for o in scoped(Order).filter_by(status="confirmed").order_by(Order.confirmed_at.desc()).limit(100).all()])


@orders_bp.route("/", methods=["POST"])
@jwt_required()
def create_order():
    user, err = _require_staff()
    if err: return err
    data  = request.get_json(silent=True) or {}
    table = str(data.get("table_name") or "").strip()[:50]
    if not table:
        return jsonify({"error": "Table name required"}), 400
    lines, total, err = build_lines(user, data.get("items"))
    if err:
        return jsonify({"error": err}), 400

    last = Order.query.filter(Order.market_id == user.market_id).order_by(Order.id.desc()).first()
    next_num = (last.id + 1) if last else 1
    order = Order(
        table_name   = table,
        cashier_id   = user.id,
        cashier_name = user.name,
        waiter_name  = str(data.get("waiter_name") or user.name)[:100],
        status       = "pending",
        total        = total,
        order_number = f"#{next_num:04d}",
        created_at   = kenya_time(),
        market_id    = user.market_id,
    )
    db.session.add(order)
    db.session.flush()
    for line in lines:
        db.session.add(OrderItem(
            order_id     = order.id,
            product_id   = line["product"].id,
            product_name = line["name"],
            quantity     = line["quantity"],
            price        = line["price"],
            subtotal     = line["subtotal"]
        ))
    db.session.commit()
    return jsonify({"message": "Order created", "id": order.id, "order_number": order.order_number, "total": total}), 201


@orders_bp.route("/<int:oid>", methods=["PUT"])
@jwt_required()
def update_order(oid):
    user, err = _require_staff()
    if err: return err
    order = load_order(oid)
    if order.status != "pending":
        return jsonify({"error": "Only pending orders can be edited"}), 400
    data = request.get_json(silent=True) or {}
    lines, total, err = build_lines(user, data.get("items"))
    if err:
        return jsonify({"error": err}), 400
    existing  = {item.product_id for item in order.items}
    submitted = {line["product"].id for line in lines}
    if existing - submitted and user.role not in ("admin", "super_admin"):
        return jsonify({"error": "Only an admin can remove items from a saved table"}), 403
    order.total = total
    OrderItem.query.filter_by(order_id=oid).delete()
    for line in lines:
        db.session.add(OrderItem(
            order_id     = oid,
            product_id   = line["product"].id,
            product_name = line["name"],
            quantity     = line["quantity"],
            price        = line["price"],
            subtotal     = line["subtotal"]
        ))
    db.session.commit()
    return jsonify({"message": "Order updated", "total": total})


@orders_bp.route("/<int:oid>/submit", methods=["POST"])
@jwt_required()
def submit_order(oid):
    _, err = _require_staff()
    if err: return err
    order = load_order(oid)
    if order.status != "pending":
        return jsonify({"error": "This order is not pending"}), 400
    data = request.get_json(silent=True) or {}
    order.status          = "submitted"
    order.payment_method  = str(data.get("payment_method") or "cash")[:50]
    order.payment_details = data.get("splits") if isinstance(data.get("splits"), list) else []
    order.submitted_at    = kenya_time()
    db.session.commit()
    return jsonify({"message": "Order submitted for confirmation"})


@orders_bp.route("/<int:oid>/confirm", methods=["POST"])
@jwt_required()
def confirm_order(oid):
    user, err = _require_cashier()
    if err: return err
    order = load_order(oid)
    if order.status != "submitted":
        return jsonify({"error": "Only submitted orders can be confirmed"}), 400
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
    audit_log("order.confirm", f"{order.order_number} {order.table_name} total {total:.2f}", user)
    return jsonify({"message": "Order confirmed", "change_due": 0})


@orders_bp.route("/<int:oid>/reject", methods=["POST"])
@jwt_required()
def reject_order(oid):
    user, err = _require_cashier()
    if err: return err
    order = load_order(oid)
    if order.status != "submitted":
        return jsonify({"error": "Only submitted orders can be rejected"}), 400
    data = request.get_json(silent=True) or {}
    order.status          = "pending"
    order.rejection_note  = str(data.get("note") or "Payment rejected by cashier")[:500]
    order.payment_method  = None
    order.payment_details = None
    order.submitted_at    = None
    db.session.commit()
    audit_log("order.reject", f"{order.order_number} {order.table_name}: {order.rejection_note}", user)
    return jsonify({"message": "Order rejected"})


@orders_bp.route("/<int:oid>", methods=["DELETE"])
@jwt_required()
def delete_order(oid):
    user, err = _require_staff()
    if err: return err
    order = load_order(oid)
    if user.role not in ("admin", "super_admin"):
        return jsonify({"error": "Only an admin can cancel an order"}), 403
    number, table, status = order.order_number, order.table_name, order.status
    OrderItem.query.filter_by(order_id=oid).delete()
    db.session.delete(order)
    db.session.commit()
    audit_log("order.delete", f"{number} {table} ({status})", user)
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
