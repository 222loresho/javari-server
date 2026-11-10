from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.category import Category
from tenant import current_user, scoped, in_venue

categories_bp = Blueprint("categories", __name__)

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
    data = request.get_json()
    c    = Category(name=data["name"], market_id=user.market_id)
    db.session.add(c)
    db.session.commit()
    return jsonify({"message": "Category created", "id": c.id}), 201

@categories_bp.route("/<int:cid>", methods=["DELETE"])
@jwt_required()
def delete_category(cid):
    c = Category.query.get_or_404(cid)
    if not in_venue(c):
        return jsonify({"error": "Category not found"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Category deleted"})
