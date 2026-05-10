from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models.user import User
from extensions import db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/pin-login", methods=["POST"])
def pin_login():
    data     = request.get_json()
    username = data.get("username", "").strip().lower()
    pin      = data.get("pin", "").strip()
    user     = User.query.filter(db.func.lower(User.username) == username).first()
    if not user or not user.active:
        return jsonify({"error": "User not found or inactive"}), 401
    if not user.pin or user.pin.strip() != pin:
        return jsonify({"error": "Wrong PIN"}), 401
    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": {"id": user.id, "name": user.name, "role": user.role}}), 200

@auth_bp.route("/verify-pin", methods=["POST"])
@jwt_required()
def verify_pin():
    data     = request.get_json()
    identity = get_jwt_identity()
    user     = User.query.get(identity)
    if not user:
        return jsonify({"valid": False}), 404
    if user.pin and user.pin.strip() == data.get("pin", "").strip():
        return jsonify({"valid": True})
    return jsonify({"valid": False})