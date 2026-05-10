from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.product import Product

products_bp = Blueprint("products", __name__)

@products_bp.route("/", methods=["GET"])
def get_products():
    return jsonify([{"id": p.id, "name": p.name, "price": float(p.price), "stock": p.stock, "category_id": p.category_id} for p in Product.query.all()])

@products_bp.route("/", methods=["POST"])
@jwt_required()
def create_product():
    data = request.get_json()
    cat  = data.get("category_id") or None
    p    = Product(name=data["name"], price=data["price"], stock=data.get("stock", 0), category_id=cat)
    db.session.add(p)
    db.session.commit()
    return jsonify({"message": "Product created"}), 201

@products_bp.route("/<int:pid>", methods=["PUT"])
@jwt_required()
def update_product(pid):
    p    = Product.query.get_or_404(pid)
    data = request.get_json()
    p.name        = data.get("name",        p.name)
    p.price       = data.get("price",       p.price)
    p.stock       = data.get("stock",       p.stock)
    p.category_id = data.get("category_id") or None
    db.session.commit()
    return jsonify({"message": "Product updated"})

@products_bp.route("/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Product deleted"})

@products_bp.route("/low-stock", methods=["GET"])
@jwt_required()
def low_stock():
    threshold = request.args.get("threshold", 10, type=int)
    products  = Product.query.filter(Product.stock <= threshold).order_by(Product.stock.asc()).all()
    return jsonify([{"id": p.id, "name": p.name, "stock": p.stock, "price": float(p.price), "category_id": p.category_id} for p in products])