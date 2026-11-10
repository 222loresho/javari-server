from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.product import Product
from tenant import current_user, scoped, in_venue

products_bp = Blueprint("products", __name__)

def serialize(p):
    return {"id": p.id, "name": p.name, "price": float(p.price), "stock": p.stock,
            "category_id": p.category_id, "image_url": p.image_url}

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
    data = request.get_json()
    cat  = data.get("category_id") or None
    p    = Product(name=data["name"], price=data["price"], stock=data.get("stock", 0),
                   category_id=cat, image_url=data.get("image_url") or None,
                   market_id=user.market_id)
    db.session.add(p)
    db.session.commit()
    return jsonify({"message": "Product created"}), 201

@products_bp.route("/<int:pid>", methods=["PUT"])
@jwt_required()
def update_product(pid):
    p    = Product.query.get_or_404(pid)
    if not in_venue(p):
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json()
    p.name        = data.get("name",        p.name)
    p.price       = data.get("price",       p.price)
    p.stock       = data.get("stock",       p.stock)
    p.category_id = data.get("category_id") or None
    if "image_url" in data:
        p.image_url = data.get("image_url") or None
    db.session.commit()
    return jsonify({"message": "Product updated"})

@products_bp.route("/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    if not in_venue(p):
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
