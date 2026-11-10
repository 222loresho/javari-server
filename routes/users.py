from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.user import User

users_bp = Blueprint("users", __name__)

STAFF_ROLES = ["cashier", "waiter"]
PROTECTED   = ["admin", "super_admin"]

def current_user():
    return User.query.get(get_jwt_identity())

def require_manager_or_admin():
    u = current_user()
    if not u or not u.active or u.role not in ("admin", "manager"):
        return None, (jsonify({"error": "Manager or admin access required"}), 403)
    if not u.market_id:
        return None, (jsonify({"error": "Your account has no venue yet. Ask the super admin."}), 403)
    return u, None

def pin_error(pin):
    if len(pin) != 4 or not pin.isdigit():
        return "PIN must be exactly 4 digits"
    return None

def resolve_manager(value, market_id):
    """None means unassigned, False means invalid, otherwise a manager id."""
    if value in ("", None):
        return None
    try:
        mid = int(value)
    except (TypeError, ValueError):
        return False
    mgr = User.query.get(mid)
    if not mgr or mgr.role != "manager" or mgr.market_id != market_id:
        return False
    return mgr.id

def serialize(u, managers):
    return {
        "id":           u.id,
        "name":         u.name,
        "username":     u.username,
        "role":         u.role,
        "active":       u.active,
        "manager_id":   u.manager_id,
        "manager_name": managers.get(u.manager_id) if u.manager_id else None,
    }

@users_bp.route("/", methods=["GET"])
@jwt_required()
def get_users():
    me, err = require_manager_or_admin()
    if err: return err
    if me.role == "admin":
        rows = User.query.filter(User.market_id == me.market_id, User.role.in_(["manager"] + STAFF_ROLES)).order_by(User.name).all()
    else:
        rows = User.query.filter(User.market_id == me.market_id, User.manager_id == me.id, User.role.in_(STAFF_ROLES)).order_by(User.name).all()
    managers = {u.id: u.name for u in User.query.filter(User.market_id == me.market_id, User.role == "manager").all()}
    return jsonify([serialize(u, managers) for u in rows])

@users_bp.route("/", methods=["POST"])
@jwt_required()
def create_user():
    me, err = require_manager_or_admin()
    if err: return err
    data     = request.get_json() or {}
    name     = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    pin      = str(data.get("pin", "")).strip()
    role     = data.get("role", "")

    if not name or not username:
        return jsonify({"error": "Name and username required"}), 400

    if me.role == "admin":
        if role != "manager":
            return jsonify({"error": "Admins add managers; managers add their staff"}), 403
    elif role not in STAFF_ROLES:
        return jsonify({"error": "Managers can only create cashier or waiter accounts"}), 403

    if not me.market_id:
        return jsonify({"error": "Your account has no venue yet. Ask the super admin."}), 400

    err = pin_error(pin)
    if err: return jsonify({"error": err}), 400
    if User.query.filter(User.market_id == me.market_id, db.func.lower(User.username) == username).first():
        return jsonify({"error": "That username is already used in this venue"}), 400

    manager_id = None if role == "manager" else me.id

    u = User(
        name=name, username=username, password="", role=role, active=True,
        pin=pin, manager_id=manager_id, market_id=me.market_id,
    )
    db.session.add(u)
    db.session.commit()
    return jsonify({"message": "User created", "id": u.id}), 201

@users_bp.route("/<int:uid>", methods=["PUT"])
@jwt_required()
def update_user(uid):
    me, err = require_manager_or_admin()
    if err: return err
    u = User.query.get(uid)
    if not u or u.market_id != me.market_id:
        return jsonify({"error": "User not found"}), 404
    if u.role in PROTECTED:
        return jsonify({"error": "Admin accounts cannot be modified here"}), 403
    if me.role == "manager" and not (u.manager_id == me.id and u.role in STAFF_ROLES):
        return jsonify({"error": "You can only manage your own staff"}), 403

    data = request.get_json() or {}
    if "name" in data:
        name = data["name"].strip()
        if not name:
            return jsonify({"error": "Name cannot be empty"}), 400
        u.name = name
    if "role" in data and data["role"] != u.role:
        new_role = data["role"]
        if me.role != "admin":
            return jsonify({"error": "Managers cannot change roles"}), 403
        if new_role not in ["manager"] + STAFF_ROLES:
            return jsonify({"error": "Role must be manager, cashier or waiter"}), 400
        if u.role == "manager" and new_role in STAFF_ROLES:
            staff = User.query.filter(User.market_id == me.market_id, User.manager_id == u.id).count()
            if staff:
                return jsonify({"error": f"{u.name} still manages {staff} staff member(s). Reassign them first."}), 400
        u.role = new_role
        if new_role == "manager":
            u.manager_id = None
    if me.role == "admin" and "manager_id" in data:
        if u.role == "manager":
            u.manager_id = None
        else:
            manager_id = resolve_manager(data.get("manager_id"), me.market_id)
            if manager_id is False:
                return jsonify({"error": "Selected manager not found"}), 400
            u.manager_id = manager_id
    if "active" in data:
        u.active = bool(data["active"])
    if data.get("pin"):
        pin = str(data["pin"]).strip()
        err = pin_error(pin)
        if err: return jsonify({"error": err}), 400
        u.pin = pin
    if u.role == "manager":
        u.manager_id = None
    elif u.role in STAFF_ROLES and not u.manager_id:
        db.session.rollback()
        return jsonify({"error": "Assign this staff member to a manager"}), 400
    db.session.commit()
    return jsonify({"message": "User updated"})

@users_bp.route("/<int:uid>", methods=["DELETE"])
@jwt_required()
def delete_user(uid):
    me, err = require_manager_or_admin()
    if err: return err
    u = User.query.get(uid)
    if not u or u.market_id != me.market_id:
        return jsonify({"error": "User not found"}), 404
    if u.role in PROTECTED:
        return jsonify({"error": "Admin accounts cannot be deleted"}), 403
    if u.id == me.id:
        return jsonify({"error": "You cannot delete your own account"}), 400
    if me.role == "manager" and not (u.manager_id == me.id and u.role in STAFF_ROLES):
        return jsonify({"error": "You can only delete your own staff"}), 403

    if u.role == "manager":
        staff = User.query.filter(User.market_id == me.market_id, User.manager_id == u.id).count()
        if staff:
            return jsonify({"error": f"{u.name} still manages {staff} staff member(s). Reassign or delete them first."}), 400
    try:
        db.session.delete(u)
        db.session.commit()
        return jsonify({"message": "User deleted"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Cannot delete user with existing orders. Deactivate them instead."}), 400
