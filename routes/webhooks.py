import hmac
import os

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from extensions import db
from models.webhook_event import WebhookEvent
from roles import require

webhooks_bp = Blueprint("webhooks", __name__)

MAX_PAYLOAD_BYTES = 256 * 1024


def _secret():
    return os.environ.get("WEBHOOK_SECRET", "").strip()


def _token_matches(value):
    secret = _secret()
    return bool(secret) and hmac.compare_digest(str(value or ""), secret)


def _event_type(payload):
    header = (request.headers.get("X-Webhook-Event") or "").strip()
    if header:
        return header[:80]
    if isinstance(payload, dict):
        for key in ("event", "event_type", "type"):
            value = payload.get(key)
            if isinstance(value, (str, int, float)):
                return str(value)[:80]
    return ""


def _store(source, token):
    if not _secret():
        return jsonify({"error": "Webhook receiver is not configured"}), 503
    header_token = request.headers.get("X-Webhook-Token")
    if not (_token_matches(token) or _token_matches(header_token)):
        return jsonify({"error": "Invalid webhook token"}), 401
    if request.content_length and request.content_length > MAX_PAYLOAD_BYTES:
        return jsonify({"error": "Payload too large"}), 413

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Body must be JSON"}), 400

    event = WebhookEvent(
        source     = str(source or "generic").strip()[:40].lower() or "generic",
        event_type = _event_type(payload),
        payload    = payload,
        ip         = (request.remote_addr or "")[:64],
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"ok": True, "id": event.id}), 200


@webhooks_bp.route("/<source>/<token>", methods=["POST"])
def receive_with_source(source, token):
    return _store(source, token)


@webhooks_bp.route("/<token>", methods=["POST"])
def receive(token):
    return _store("generic", token)


@webhooks_bp.route("/events", methods=["GET"])
@jwt_required()
def list_events():
    _, err = require()  # super admins only
    if err: return err
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(200, limit))
    source = (request.args.get("source") or "").strip().lower()
    query = WebhookEvent.query
    if source:
        query = query.filter(WebhookEvent.source == source[:40])
    events = query.order_by(WebhookEvent.received_at.desc()).limit(limit).all()
    return jsonify([{
        "id":          e.id,
        "source":      e.source,
        "event_type":  e.event_type,
        "payload":     e.payload,
        "ip":          e.ip,
        "received_at": e.received_at.isoformat(),
    } for e in events])
