from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from extensions import db
from models.category import Category

categories_bp = Blueprint("categories", __name__)

@categories_bp.route("/", methods=["GET"])
def get_categories():
    return jsonify([{"id": c.id, "name": c.name} for c in Category.query.all()])

@categories_bp.route("/", methods=["POST"])
@jwt_required()
def create_category():
    data = request.get_json()
    c    = Category(name=data["name"])
    db.session.add(c)
    db.session.commit()
    return jsonify({"message": "Category created", "id": c.id}), 201

@categories_bp.route("/<int:cid>", methods=["DELETE"])
@jwt_required()
def delete_category(cid):
    c = Category.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Category deleted"})