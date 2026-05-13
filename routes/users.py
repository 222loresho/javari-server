from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.user import User

users_bp = Blueprint("users", __name__)

def current_user():
    return User.query.get(get_jwt_identity())

def admin_required():
    u = current_user()
    if not u or u.role != "admin":
        return jsonify({"error": "Admin access required"}), 403

@users_bp.route("/", methods=["GET"])
@jwt_required()
def get_users():
    err = admin_required()
    if err: return err
    allowed = ["cashier", "waiter"]
    return jsonify([{"id": u.id, "name": u.name, "username": u.username, "role": u.role, "active": u.active, "pin": u.pin} for u in User.query.all() if u.role in allowed])

@users_bp.route("/", methods=["POST"])
@jwt_required()
def create_user():
    err      = admin_required()
    if err: return err
    data     = request.get_json()
    name     = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    pin      = str(data.get("pin", "1234")).strip()
    role     = data.get("role", "cashier")
    if not name or not username:
        return jsonify({"error": "Name and username required"}), 400
    if len(pin) != 4 or not pin.isdigit():
        return jsonify({"error": "PIN must be exactly 4 digits"}), 400
    if role in ["admin", "super_admin"]:
        return jsonify({"error": "Only super admin can create admin accounts"}), 403
    if User.query.filter(db.func.lower(User.username) == username).first():
        return jsonify({"error": "Username already exists"}), 400
    u = User(name=name, username=username, password="", role=role, active=True, pin=pin)
    db.session.add(u)
    db.session.commit()
    return jsonify({"message": "User created", "id": u.id}), 201

@users_bp.route("/<int:uid>", methods=["PUT"])
@jwt_required()
def update_user(uid):
    err  = admin_required()
    if err: return err
    u    = User.query.get_or_404(uid)
    if u.role in ["admin","super_admin"]:
        return jsonify({"error": "Only super admin can manage admin accounts"}), 403
    data = request.get_json()
    if "name"   in data: u.name   = data["name"].strip()
    if "role"   in data:
        if data["role"] in ["admin","super_admin"]:
            return jsonify({"error": "Only super admin can assign admin roles"}), 403
        u.role = data["role"]
    if "active" in data: u.active = data["active"]
    if "pin" in data and data["pin"]:
        pin = str(data["pin"]).strip()
        if len(pin) != 4 or not pin.isdigit():
            return jsonify({"error": "PIN must be exactly 4 digits"}), 400
        u.pin = pin
    db.session.commit()
    return jsonify({"message": "User updated"})

@users_bp.route("/<int:uid>", methods=["DELETE"])
@jwt_required()
def delete_user(uid):
    err = admin_required()
    if err: return err
    if current_user().id == uid:
        return jsonify({"error": "Cannot delete yourself"}), 400
    u = User.query.get_or_404(uid)
    if u.role in ["admin","super_admin"]:
        return jsonify({"error": "Only super admin can delete admin accounts"}), 403
    try:
        db.session.delete(u)
        db.session.commit()
        return jsonify({"message": "User deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Cannot delete user with existing orders. Deactivate them instead."}), 400