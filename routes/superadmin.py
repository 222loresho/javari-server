from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.user import User
from models.market import Market
from models.sale import Sale
from models.order import Order
from models.product import Product
from models.category import Category
from venue_codes import venue_code_for
from pin_auth import hash_pin
from audit import log as audit_log
from models.audit_log import AuditLog
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

superadmin_bp = Blueprint("superadmin", __name__)
KENYA_TZ      = timezone(timedelta(hours=3))

def require_superadmin():
    uid  = get_jwt_identity()
    user = User.query.get(uid)
    if not user or not user.active or user.role != "super_admin":
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
    d    = request.get_json(silent=True) or {}
    name = str(d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Venue name required"}), 400
    code = venue_code_for(name, {m.code.upper() for m in Market.query.all() if m.code})
    m = Market(
        name          = name,
        code          = code,
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
    audit_log("market.create", f"{m.name} ({m.code})")
    return jsonify({"message": "Market created", "id": m.id, "code": m.code}), 201

@superadmin_bp.route("/markets/<int:mid>", methods=["PUT"])
@jwt_required()
def update_market(mid):
    err = require_superadmin()
    if err: return err
    m = Market.query.get_or_404(mid)
    d = request.get_json(silent=True) or {}
    if "code" in d and (d["code"] or "").strip().upper() != (m.code or ""):
        return jsonify({"error": "Venue codes are permanent and cannot be changed"}), 400
    for field in ["name","location","contact_name","contact_email","contact_phone","plan","monthly_fee","currency","status","api_url","notes"]:
        if field in d: setattr(m, field, d[field])
    if "last_payment" in d and d["last_payment"]:
        m.last_payment = datetime.fromisoformat(d["last_payment"])
    if "next_payment" in d and d["next_payment"]:
        m.next_payment = datetime.fromisoformat(d["next_payment"])
    db.session.commit()
    audit_log("market.update", f"{m.name} ({m.code}): {', '.join(sorted(d.keys())) or 'no changes'}")
    return jsonify({"message": "Market updated"})

@superadmin_bp.route("/markets/<int:mid>", methods=["DELETE"])
@jwt_required()
def delete_market(mid):
    err = require_superadmin()
    if err: return err
    m = Market.query.get_or_404(mid)
    refs = {
        "user(s)":     User.query.filter_by(market_id=mid).count(),
        "product(s)":  Product.query.filter_by(market_id=mid).count(),
        "category(ies)": Category.query.filter_by(market_id=mid).count(),
        "sale(s)":     Sale.query.filter_by(market_id=mid).count(),
        "order(s)":    Order.query.filter_by(market_id=mid).count(),
    }
    used = [f"{count} {label}" for label, count in refs.items() if count]
    if used:
        return jsonify({"error": f"This venue still has {', '.join(used)}. Reassign or remove them first."}), 400
    name, code = m.name, m.code
    db.session.delete(m)
    db.session.commit()
    audit_log("market.delete", f"{name} ({code})")
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
    markets = {m.id: m.name for m in Market.query.all()}
    return jsonify([{
        "id": u.id, "name": u.name, "username": u.username, "role": u.role,
        "active": u.active, "market_id": u.market_id,
        "market_name": markets.get(u.market_id),
    } for u in users])

@superadmin_bp.route("/users", methods=["POST"])
@jwt_required()
def create_user():
    err = require_superadmin()
    if err: return err
    d    = request.get_json(silent=True) or {}
    name = str(d.get("name") or "").strip()[:100]
    username = str(d.get("username") or "").strip().lower()[:50]
    pin  = str(d.get("pin") or "").strip()
    role = d.get("role","admin")
    if role not in ("admin", "super_admin"):
        return jsonify({"error": "Super admins create admins for a venue"}), 400
    market_id = d.get("market_id")
    if role == "super_admin":
        market_id = None
    else:
        if market_id in ("", None):
            return jsonify({"error": "Select a venue for this account"}), 400
        try:
            market_id = int(market_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid venue"}), 400
        if not Market.query.get(market_id):
            return jsonify({"error": "Venue not found"}), 400
    if not name or not username:
        return jsonify({"error": "Name and username required"}), 400
    if len(pin) != 4 or not pin.isdigit():
        return jsonify({"error": "PIN must be 4 digits"}), 400
    if User.query.filter(User.market_id == market_id, db.func.lower(User.username) == username).first():
        return jsonify({"error": "That username is already used in this venue"}), 400
    u = User(name=name, username=username, password="", role=role, active=True,
             pin=hash_pin(pin), pin_length=4, market_id=market_id)
    db.session.add(u)
    db.session.commit()
    audit_log("user.create", f"{role} {username} in venue {market_id}")
    return jsonify({"message": "User created", "id": u.id}), 201

@superadmin_bp.route("/audit", methods=["GET"])
@jwt_required()
def audit_trail():
    err = require_superadmin()
    if err: return err
    rows = AuditLog.query.order_by(AuditLog.id.desc()).limit(200).all()
    return jsonify([{
        "id":         a.id,
        "actor_id":   a.actor_id,
        "actor_name": a.actor_name,
        "action":     a.action,
        "detail":     a.detail,
        "ip":         a.ip,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows])

def serialize_market(m):
    return {
        "id":            m.id,
        "name":          m.name,
        "code":          m.code,
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