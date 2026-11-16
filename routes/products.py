from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.product import Product
from models.category import Category
from tenant import current_user, scoped, in_venue

products_bp = Blueprint("products", __name__)

UNITS = ("pc", "kg", "g", "l", "ml", "pack", "dozen", "bunch")


def serialize(p):
    return {"id": p.id, "name": p.name, "price": float(p.price), "stock": p.stock,
            "category_id": p.category_id, "image_url": p.image_url,
            "barcode": p.barcode, "unit": p.unit or "pc"}


def _admin_error(user):
    if not user or user.role not in ("admin", "super_admin"):
        return jsonify({"error": "Admin access required"}), 403
    return None


def _price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def _stock(value):
    try:
        stock = int(value)
    except (TypeError, ValueError):
        return None
    return stock if stock >= 0 else None


def _barcode(value):
    return str(value or "").strip()[:40] or None


def _unit(value):
    unit = str(value or "").strip().lower() or "pc"
    return unit if unit in UNITS else None


def _barcode_taken(code, market_id, exclude_id=None):
    if not code:
        return False
    query = Product.query.filter(Product.barcode == code, Product.market_id == market_id)
    if exclude_id is not None:
        query = query.filter(Product.id != exclude_id)
    return query.first() is not None


def _category_ok(cat_id, user):
    if cat_id in (None, ""):
        return True
    try:
        cat_id = int(cat_id)
    except (TypeError, ValueError):
        return False
    category = Category.query.get(cat_id)
    if not category:
        return False
    return user.role == "super_admin" or category.market_id == user.market_id


@products_bp.route("/", methods=["GET"])
@jwt_required(optional=True)
def get_products():
    user = current_user()
    # Anonymous callers (customer QR menu) only ever see the legacy, unassigned menu.
    query = Product.query.filter(Product.market_id.is_(None)) if user is None else scoped(Product, user)
    return jsonify([serialize(p) for p in query.all()])


@products_bp.route("/", methods=["POST"])
@jwt_required()
def create_product():
    user = current_user()
    err = _admin_error(user)
    if err: return err
    data  = request.get_json(silent=True) or {}
    name  = str(data.get("name") or "").strip()[:100]
    price = _price(data.get("price"))
    stock = _stock(data.get("stock", 0))
    cat   = data.get("category_id") or None
    barcode = _barcode(data.get("barcode"))
    unit    = _unit(data.get("unit"))
    if not name:
        return jsonify({"error": "Product name required"}), 400
    if price is None:
        return jsonify({"error": "Price must be a positive number"}), 400
    if stock is None:
        return jsonify({"error": "Stock must be zero or more"}), 400
    if not _category_ok(cat, user):
        return jsonify({"error": "Unknown category"}), 400
    if unit is None:
        return jsonify({"error": "Unit must be one of: " + ", ".join(UNITS)}), 400
    if _barcode_taken(barcode, user.market_id):
        return jsonify({"error": "Barcode already used by another product"}), 409
    p = Product(name=name, price=price, stock=stock,
                category_id=cat, image_url=str(data.get("image_url") or "")[:500] or None,
                market_id=user.market_id, barcode=barcode, unit=unit)
    db.session.add(p)
    db.session.commit()
    return jsonify({"message": "Product created"}), 201


@products_bp.route("/<int:pid>", methods=["PUT"])
@jwt_required()
def update_product(pid):
    user = current_user()
    err = _admin_error(user)
    if err: return err
    p = Product.query.get_or_404(pid)
    if not in_venue(p, user):
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = str(data.get("name") or "").strip()[:100]
        if not name:
            return jsonify({"error": "Product name required"}), 400
        p.name = name
    if "price" in data:
        price = _price(data.get("price"))
        if price is None:
            return jsonify({"error": "Price must be a positive number"}), 400
        p.price = price
    if "stock" in data:
        stock = _stock(data.get("stock"))
        if stock is None:
            return jsonify({"error": "Stock must be zero or more"}), 400
        p.stock = stock
    if "category_id" in data:
        cat = data.get("category_id") or None
        if not _category_ok(cat, user):
            return jsonify({"error": "Unknown category"}), 400
        p.category_id = cat
    if "image_url" in data:
        p.image_url = str(data.get("image_url") or "")[:500] or None
    if "barcode" in data:
        barcode = _barcode(data.get("barcode"))
        if _barcode_taken(barcode, p.market_id, exclude_id=p.id):
            return jsonify({"error": "Barcode already used by another product"}), 409
        p.barcode = barcode
    if "unit" in data:
        unit = _unit(data.get("unit"))
        if unit is None:
            return jsonify({"error": "Unit must be one of: " + ", ".join(UNITS)}), 400
        p.unit = unit
    db.session.commit()
    return jsonify({"message": "Product updated"})


@products_bp.route("/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_product(pid):
    user = current_user()
    err = _admin_error(user)
    if err: return err
    p = Product.query.get_or_404(pid)
    if not in_venue(p, user):
        return jsonify({"error": "Product not found"}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Product deleted"})


@products_bp.route("/low-stock", methods=["GET"])
@jwt_required()
def low_stock():
    threshold = request.args.get("threshold", 10, type=int)
    products  = scoped(Product).filter(Product.stock <= threshold).order_by(Product.stock.asc()).all()
    return jsonify([serialize(p) for p in products])
