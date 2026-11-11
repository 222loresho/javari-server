"""Append-only record of sensitive actions, readable by super admins."""
from flask import has_request_context, request

from extensions import db
from models.audit_log import AuditLog


def log(action, detail="", actor=None):
    try:
        if actor is None:
            try:
                from tenant import current_user
                actor = current_user()
            except Exception:
                actor = None
        ip = (request.remote_addr or "") if has_request_context() else ""
        db.session.add(AuditLog(
            actor_id   = getattr(actor, "id", None),
            actor_name = (getattr(actor, "username", "") or "")[:100],
            action     = str(action)[:60],
            detail     = str(detail)[:500],
            ip         = ip[:64],
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
