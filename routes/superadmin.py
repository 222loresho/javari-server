from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.user import User
from models.market import Market
from models.sale import Sale
from models.order import Order
from models.product import Product
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

superadmin_bp = Blueprint("superadmin", __name__)
KENYA_TZ      = timezone(timedelta(hours=3))

def require_superadmin():
    uid  = get_jwt_identity()
    user = User.query.get(uid)
    if not user or user.role != "super_admin":
        return jsonify({"error": "Super admin access required"}), 403
    return None

# ── Markets ──────────────────────────────────────────────────────────────────
@superadmin_bp.route("/markets", methods=["GET"])
@jwt_required()
def get_markets():
    err = require_superadmin()
    if err: return err
    markets = Market.query.order_by(Market.created_at.desc()).all()
    return jsonify([serialize_market(m) for m in markets])

@superadmin_bp.route("/markets", methods=["POST"])
@jwt_required()
def create_market():
    err = require_superadmin()
    if err: return err
    d = request.get_json()
    m = Market(
        name          = d.get("name","").strip(),
        location      = d.get("location",""),
        contact_name  = d.get("contact_name",""),
        contact_email = d.get("contact_email",""),
        contact_phone = d.get("contact_phone",""),
        plan          = d.get("plan","trial"),
        monthly_fee   = d.get("monthly_fee", 0),
        currency      = d.get("currency","KES"),
        status        = d.get("status","trial"),
        api_url       = d.get("api_url",""),
        notes         = d.get("notes",""),
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({"message": "Market created", "id": m.id}), 201

@superadmin_bp.route("/markets/<int:mid>", methods=["PUT"])
@jwt_required()
def update_market(mid):
    err = require_superadmin()
    if err: return err
    m = Market.query.get_or_404(mid)
    d = request.get_json()
    for field in ["name","location","contact_name","contact_email","contact_phone","plan","monthly_fee","currency","status","api_url","notes"]:
        if field in d: setattr(m, field, d[field])
    if "last_payment" in d and d["last_payment"]:
        m.last_payment = datetime.fromisoformat(d["last_payment"])
    if "next_payment" in d and d["next_payment"]:
        m.next_payment = datetime.fromisoformat(d["next_payment"])
    db.session.commit()
    return jsonify({"message": "Market updated"})

@superadmin_bp.route("/markets/<int:mid>", methods=["DELETE"])
@jwt_required()
def delete_market(mid):
    err = require_superadmin()
    if err: return err
    m = Market.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    return jsonify({"message": "Market deleted"})

# ── Dashboard analytics ───────────────────────────────────────────────────────
@superadmin_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    err = require_superadmin()
    if err: return err

    markets = Market.query.all()
    total_markets    = len(markets)
    active_markets   = len([m for m in markets if m.status == "active"])
    trial_markets    = len([m for m in markets if m.status == "trial"])
    suspended        = len([m for m in markets if m.status == "suspended"])
    monthly_revenue  = float(sum(m.monthly_fee or 0 for m in markets if m.status == "active"))

    # Sales analytics (from this deployment)
    today      = datetime.now(KENYA_TZ).date()
    month_start= today.replace(day=1)

    today_sales = Sale.query.filter(func.date(Sale.created_at) == today).all()
    month_sales = Sale.query.filter(func.date(Sale.created_at) >= str(month_start)).all()

    today_revenue = float(sum(s.total for s in today_sales))
    month_revenue = float(sum(s.total for s in month_sales))

    # Recent 7 days trend
    trend = []
    for i in range(6, -1, -1):
        day   = (datetime.now(KENYA_TZ) - timedelta(days=i)).date()
        sales = Sale.query.filter(func.date(Sale.created_at) == str(day)).all()
        trend.append({"date": str(day), "revenue": float(sum(s.total for s in sales)), "count": len(sales)})

    # Plan distribution
    plans = {}
    for m in markets:
        plans[m.plan] = plans.get(m.plan, 0) + 1

    # Upcoming payments (next 7 days)
    upcoming = []
    now = datetime.now(KENYA_TZ).replace(tzinfo=None)
    for m in markets:
        if m.next_payment and m.status == "active":
            days_left = (m.next_payment - now).days
            if 0 <= days_left <= 7:
                upcoming.append({"market": m.name, "amount": float(m.monthly_fee or 0), "days_left": days_left, "date": m.next_payment.isoformat()})

    return jsonify({
        "markets": {
            "total":     total_markets,
            "active":    active_markets,
            "trial":     trial_markets,
            "suspended": suspended,
        },
        "subscription_revenue": monthly_revenue,
        "sales": {
            "today_revenue": today_revenue,
            "today_count":   len(today_sales),
            "month_revenue": month_revenue,
            "month_count":   len(month_sales),
        },
        "trend":    trend,
        "plans":    plans,
        "upcoming": upcoming,
    })

# ── All users ─────────────────────────────────────────────────────────────────
@superadmin_bp.route("/users", methods=["GET"])
@jwt_required()
def all_users():
    err = require_superadmin()
    if err: return err
    users = User.query.order_by(User.id).all()
    return jsonify([{"id": u.id, "name": u.name, "username": u.username, "role": u.role, "active": u.active} for u in users])

@superadmin_bp.route("/users", methods=["POST"])
@jwt_required()
def create_user():
    err = require_superadmin()
    if err: return err
    d    = request.get_json()
    name = d.get("name","").strip()
    username = d.get("username","").strip().lower()
    pin  = str(d.get("pin","1234")).strip()
    role = d.get("role","admin")
    if not name or not username:
        return jsonify({"error": "Name and username required"}), 400
    if len(pin) != 4 or not pin.isdigit():
        return jsonify({"error": "PIN must be 4 digits"}), 400
    if User.query.filter(db.func.lower(User.username) == username).first():
        return jsonify({"error": "Username already exists"}), 400
    u = User(name=name, username=username, password="", role=role, active=True, pin=pin)
    db.session.add(u)
    db.session.commit()
    return jsonify({"message": "User created", "id": u.id}), 201

def serialize_market(m):
    return {
        "id":            m.id,
        "name":          m.name,
        "location":      m.location,
        "contact_name":  m.contact_name,
        "contact_email": m.contact_email,
        "contact_phone": m.contact_phone,
        "plan":          m.plan,
        "monthly_fee":   float(m.monthly_fee or 0),
        "currency":      m.currency,
        "status":        m.status,
        "api_url":       m.api_url,
        "notes":         m.notes,
        "created_at":    m.created_at.isoformat() if m.created_at else None,
        "last_payment":  m.last_payment.isoformat() if m.last_payment else None,
        "next_payment":  m.next_payment.isoformat() if m.next_payment else None,
    }