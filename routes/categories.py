from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.category import Category
from models.product import Product
from tenant import current_user, scoped, in_venue

categories_bp = Blueprint("categories", __name__)


def _admin_error(user):
    if not user or user.role not in ("admin", "super_admin"):
        return jsonify({"error": "Admin access required"}), 403
    return None


@categories_bp.route("/", methods=["GET"])
@jwt_required(optional=True)
def get_categories():
    user  = current_user()
    query = Category.query.filter(Category.market_id.is_(None)) if user is None else scoped(Category, user)
    return jsonify([{"id": c.id, "name": c.name} for c in query.all()])


@categories_bp.route("/", methods=["POST"])
@jwt_required()
def create_category():
    user = current_user()
    err = _admin_error(user)
    if err: return err
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:100]
    if not name:
        return jsonify({"error": "Category name required"}), 400
    c = Category(name=name, market_id=user.market_id)
    db.session.add(c)
    db.session.commit()
    return jsonify({"message": "Category created", "id": c.id}), 201


@categories_bp.route("/<int:cid>", methods=["DELETE"])
@jwt_required()
def delete_category(cid):
    user = current_user()
    err = _admin_error(user)
    if err: return err
    c = Category.query.get_or_404(cid)
    if not in_venue(c, user):
        return jsonify({"error": "Category not found"}), 404
    Product.query.filter(Product.category_id == c.id).update({"category_id": None})
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Category deleted"})
