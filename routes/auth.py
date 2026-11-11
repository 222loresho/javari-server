from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models.user import User
from models.market import Market
from extensions import db
from pin_auth import burn_check, hash_pin, is_hashed, pin_matches
from login_throttle import (
    check_login,
    record_login,
    check_stepup,
    fail_stepup,
    reset_stepup,
)
from audit import log as audit_log

auth_bp = Blueprint("auth", __name__)

BAD_LOGIN = "Wrong username or PIN"


def _pin_matches(user, pin):
    return pin_matches(user.pin, pin)


def _upgrade_pin(user, pin):
    """Re-hash legacy plaintext PINs the first time they are used."""
    if is_hashed(user.pin or ""):
        return
    user.pin = hash_pin(pin)
    user.pin_length = len(pin)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _too_many(retry):
    return jsonify({
        "error": f"Too many attempts. Try again in {retry} seconds.",
        "retry_after": retry,
    }), 429


@auth_bp.route("/pin-login", methods=["POST"])
def pin_login():
    data     = request.get_json(silent=True) or {}
    code     = str(data.get("code") or "").strip().upper()[:12]
    username = str(data.get("username") or "").strip().lower()[:50]
    pin      = str(data.get("pin") or "").strip()[:16]

    if not username:
        return jsonify({"error": "Enter your username"}), 400

    user_key = username
    retry    = check_login(username, request.remote_addr)
    if retry:
        return _too_many(retry)

    if code:
        market = Market.query.filter(db.func.upper(Market.code) == code).first()
        user = None
        if market:
            user = User.query.filter(
                User.market_id == market.id,
                db.func.lower(User.username) == username,
            ).first()
        if not user or not user.active or not _pin_matches(user, pin):
            if not user:
                burn_check(pin)
            record_login(user_key, request.remote_addr, False)
            return jsonify({"error": BAD_LOGIN}), 401
    else:
        matches = User.query.filter(
            User.active.is_(True),
            db.func.lower(User.username) == username,
        ).all()
        hits = [u for u in matches if _pin_matches(u, pin)]
        if not hits:
            if not matches:
                burn_check(pin)
            record_login(user_key, request.remote_addr, False)
            return jsonify({"error": BAD_LOGIN}), 401
        if len(hits) > 1:
            return jsonify({"error": "This username and PIN exist in two venues. Ask your admin to change one PIN."}), 409
        user = hits[0]

    if user.role != "super_admin":
        if not user.market_id:
            record_login(user_key, request.remote_addr, False)
            return jsonify({"error": "No venue assigned to this account. Ask the super admin."}), 403
        if user.role in ("cashier", "waiter") and not user.manager_id:
            record_login(user_key, request.remote_addr, False)
            return jsonify({"error": "No manager assigned yet. Ask your admin."}), 403

    record_login(user_key, request.remote_addr, True)
    _upgrade_pin(user, pin)
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
        "pin_length": user.pin_length or 4,
    }), 200


@auth_bp.route("/verify-pin", methods=["POST"])
@jwt_required()
def verify_pin():
    data = request.get_json(silent=True) or {}
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"valid": False}), 404
    key   = f"pincheck:{user.id}"
    retry = check_stepup(key)
    if retry:
        return _too_many(retry)
    if _pin_matches(user, str(data.get("pin") or "").strip()[:16]):
        reset_stepup(key)
        return jsonify({"valid": True})
    fail_stepup(key)
    return jsonify({"valid": False})


@auth_bp.route("/change-pin", methods=["POST"])
@jwt_required()
def change_pin():
    data    = request.get_json(silent=True) or {}
    current = str(data.get("current_pin") or "").strip()[:16]
    new_pin = str(data.get("new_pin") or "").strip()
    user    = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    key   = f"pincheck:{user.id}"
    retry = check_stepup(key)
    if retry:
        return _too_many(retry)
    if not _pin_matches(user, current):
        fail_stepup(key)
        return jsonify({"error": "Current PIN is incorrect"}), 401
    if len(new_pin) != 4 or not new_pin.isdigit():
        return jsonify({"error": "PIN must be exactly 4 digits"}), 400
    if new_pin == current:
        return jsonify({"error": "New PIN must be different"}), 400
    user.pin = hash_pin(new_pin)
    user.pin_length = 4
    db.session.commit()
    reset_stepup(key)
    audit_log("pin.change", f"{user.username} changed their own PIN", user)
    return jsonify({"message": "PIN updated", "pin_length": 4})
