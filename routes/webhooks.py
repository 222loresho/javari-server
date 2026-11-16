import hashlib
import hmac
import json
import os

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from extensions import db
from models.audit_log import AuditLog
from models.webhook_event import WebhookEvent
from roles import require

webhooks_bp = Blueprint("webhooks", __name__)

MAX_PAYLOAD_BYTES = 256 * 1024
SIGNED_SOURCES = ("github",)


def _secret():
    return os.environ.get("WEBHOOK_SECRET", "").strip()


def _token_matches(value):
    secret = _secret()
    return bool(secret) and hmac.compare_digest(str(value or ""), secret)


def _signature_matches(raw):
    header = (request.headers.get("X-Hub-Signature-256") or "").strip()
    if not header.startswith("sha256="):
        return False
    digest = hmac.new(_secret().encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header, "sha256=" + digest)


def _event_type(payload):
    for name in ("X-Webhook-Event", "X-GitHub-Event"):
        header = (request.headers.get(name) or "").strip()
        if header:
            return header[:80]
    if isinstance(payload, dict):
        for key in ("event", "event_type", "type"):
            value = payload.get(key)
            if isinstance(value, (str, int, float)):
                return str(value)[:80]
    return ""


def _store(source, token):
    secret = _secret()
    if not secret:
        return jsonify({"error": "Webhook receiver is not configured"}), 503
    header_token = request.headers.get("X-Webhook-Token")
    if not (_token_matches(token) or _token_matches(header_token)):
        return jsonify({"error": "Invalid webhook token"}), 401

    raw = request.get_data(cache=True)
    if len(raw) > MAX_PAYLOAD_BYTES:
        return jsonify({"error": "Payload too large"}), 413

    source = str(source or "generic").strip()[:40].lower() or "generic"
    if source in SIGNED_SOURCES and not _signature_matches(raw):
        return jsonify({"error": "Missing or invalid X-Hub-Signature-256 - the signing secret must match WEBHOOK_SECRET"}), 401

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return jsonify({"error": "Body must be JSON"}), 400

    event = WebhookEvent(
        source     = source,
        event_type = _event_type(payload),
        delivery   = (request.headers.get("X-GitHub-Delivery") or "")[:64] or None,
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


@webhooks_bp.route("/config", methods=["GET"])
@jwt_required()
def config():
    user, err = require()  # super admins only
    if err: return err
    secret = _secret()
    base = (os.environ.get("PUBLIC_BASE_URL") or request.url_root).rstrip("/")
    if secret:
        db.session.add(AuditLog(
            actor_id   = user.id,
            actor_name = user.name,
            action     = "webhook_url_viewed",
            detail     = "github",
            ip         = (request.remote_addr or "")[:64],
        ))
        db.session.commit()
    return jsonify({
        "configured":  bool(secret),
        "source":      "github",
        "url":         f"{base}/api/webhooks/github/{secret}" if secret else "",
        "signing":     "X-Hub-Signature-256 must be signed with the same secret",
    })


@webhooks_bp.route("/events", methods=["GET"])
@jwt_required()
def list_events():
    user, err = require()  # super admins only
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
        "delivery":    e.delivery,
        "payload":     e.payload,
        "ip":          e.ip,
        "received_at": e.received_at.isoformat(),
    } for e in events])
