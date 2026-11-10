from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models.user import User
from models.market import Market
from extensions import db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/pin-login", methods=["POST"])
def pin_login():
    data     = request.get_json() or {}
    code     = (data.get("code") or "").strip().upper()
    username = data.get("username", "").strip().lower()
    pin      = str(data.get("pin", "")).strip()

    if not username:
        return jsonify({"error": "Enter your username"}), 400

    if code:
        market = Market.query.filter(db.func.upper(Market.code) == code).first()
        if not market:
            return jsonify({"error": "Unknown venue code"}), 404
        user = User.query.filter(
            User.market_id == market.id,
            db.func.lower(User.username) == username,
        ).first()
        if not user or not user.active:
            return jsonify({"error": "User not found or inactive"}), 401
        if not user.pin or user.pin.strip() != pin:
            return jsonify({"error": "Wrong PIN"}), 401
    else:
        matches = User.query.filter(
            User.active.is_(True),
            db.func.lower(User.username) == username,
        ).all()
        if not matches:
            return jsonify({"error": "User not found or inactive"}), 401
        hits = [u for u in matches if u.pin and u.pin.strip() == pin]
        if not hits:
            return jsonify({"error": "Wrong PIN"}), 401
        if len(hits) > 1:
            return jsonify({"error": "This username and PIN exist in two venues. Ask your admin to change one PIN."}), 409
        user = hits[0]

    if user.role != "super_admin":
        if not user.market_id:
            return jsonify({"error": "No venue assigned to this account. Ask the super admin."}), 403
        if user.role in ("cashier", "waiter") and not user.manager_id:
            return jsonify({"error": "No manager assigned yet. Ask your admin."}), 403
    token = create_access_token(identity=str(user.id))
    market = Market.query.get(user.market_id) if user.market_id else None
    return jsonify({
        "token": token,
        "user": {
            "id": user.id, "name": user.name, "role": user.role,
            "market_id": user.market_id,
            "market_name": market.name if market else None,
            "market_code": market.code if market else None,
        },
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
    if len(new_pin) != 4 or not new_pin.isdigit():
        return jsonify({"error": "PIN must be exactly 4 digits"}), 400
    if new_pin == current:
        return jsonify({"error": "New PIN must be different"}), 400
    user.pin = new_pin
    db.session.commit()
    return jsonify({"message": "PIN updated", "pin_length": 4})