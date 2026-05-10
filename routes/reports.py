from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models.sale import Sale, SaleItem
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

reports_bp = Blueprint("reports", __name__)
KENYA_TZ   = timezone(timedelta(hours=3))

@reports_bp.route("/daily", methods=["GET"])
@jwt_required()
def daily_report():
    date_str = request.args.get("date", datetime.now(KENYA_TZ).date().isoformat())
    try:    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return jsonify({"error": "Invalid date"}), 400
    sales     = Sale.query.filter(func.date(Sale.created_at) == target).all()
    total_rev = float(sum(s.total for s in sales))
    by_method = {}
    for s in sales:
        m = s.payment_method or "cash"
        if m not in by_method: by_method[m] = {"count": 0, "total": 0}
        by_method[m]["count"] += 1
        by_method[m]["total"] += float(s.total)
    item_map = {}
    for s in sales:
        for i in s.items:
            if i.product_id not in item_map:
                item_map[i.product_id] = {"product_name": i.product_name, "quantity": 0, "revenue": 0}
            item_map[i.product_id]["quantity"] += i.quantity
            item_map[i.product_id]["revenue"]  += float(i.subtotal)
    all_items  = sorted(item_map.values(), key=lambda x: x["quantity"], reverse=True)
    sales_list = [{
        "id": s.id, "cashier_name": s.cashier_name,
        "total": float(s.total), "amount_paid": float(s.amount_paid),
        "change_due": float(s.change_due), "payment_method": s.payment_method,
        "created_at": s.created_at.isoformat(),
        "items": [{"product_name": i.product_name, "quantity": i.quantity, "subtotal": float(i.subtotal)} for i in s.items]
    } for s in sales]
    return jsonify({
        "date": date_str, "total_revenue": total_rev,
        "total_transactions": len(sales), "by_payment_method": by_method,
        "top_products": all_items[:10], "all_items": all_items, "sales": sales_list
    })

@reports_bp.route("/revenue", methods=["GET"])
@jwt_required()
def revenue_chart():
    from datetime import timedelta as td
    period = request.args.get("period", "weekly")
    now    = datetime.now(KENYA_TZ)
    if period == "daily":
        sales   = Sale.query.filter(func.date(Sale.created_at) == now.date()).all()
        buckets = {f"{h:02d}:00": 0 for h in range(24)}
        for s in sales: buckets[f"{s.created_at.hour:02d}:00"] += float(s.total)
    elif period == "weekly":
        days    = [(now - td(days=i)).date() for i in range(6,-1,-1)]
        buckets = {str(d): 0 for d in days}
        for s in Sale.query.filter(func.date(Sale.created_at) >= str(days[0])).all():
            key = str(s.created_at.date())
            if key in buckets: buckets[key] += float(s.total)
    elif period == "monthly":
        days    = [(now - td(days=i)).date() for i in range(29,-1,-1)]
        buckets = {str(d): 0 for d in days}
        for s in Sale.query.filter(func.date(Sale.created_at) >= str(days[0])).all():
            key = str(s.created_at.date())
            if key in buckets: buckets[key] += float(s.total)
    else:
        buckets = {}
        for i in range(11,-1,-1):
            m = (now.replace(day=1) - td(days=i*30)).strftime("%Y-%m")
            buckets[m] = 0
        for s in Sale.query.all():
            key = s.created_at.strftime("%Y-%m")
            if key in buckets: buckets[key] += float(s.total)
    data  = [{"label": k, "revenue": v} for k, v in buckets.items()]
    total = sum(d["revenue"] for d in data)
    peak  = max(data, key=lambda x: x["revenue"]) if data else None
    return jsonify({"period": period, "data": data, "total": total, "peak": peak})