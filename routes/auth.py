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
    return jsonify({
        "token": token,
        "user": {"id": user.id, "name": user.name, "role": user.role},
        "pin_length": len(user.pin or ""),
    }), 200

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

@auth_bp.route("/change-pin", methods=["POST"])
@jwt_required()
def change_pin():
    data    = request.get_json() or {}
    current = str(data.get("current_pin", "")).strip()
    new_pin = str(data.get("new_pin", "")).strip()
    user    = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    if not user.pin or user.pin.strip() != current:
        return jsonify({"error": "Current PIN is incorrect"}), 401
    required = 6 if user.role in ("admin", "super_admin") else 4
    if len(new_pin) != required or not new_pin.isdigit():
        return jsonify({"error": f"PIN must be exactly {required} digits"}), 400
    if new_pin == current:
        return jsonify({"error": "New PIN must be different"}), 400
    user.pin = new_pin
    db.session.commit()
    return jsonify({"message": "PIN updated", "pin_length": required})