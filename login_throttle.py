"""PIN attempt throttling.

Login attempts are stored in the database so the limits survive restarts and
deploys. Short-lived step-up PIN checks (verify/change) use an in-process
window, which is enough because the account is already authenticated.
"""
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from extensions import db
from models.login_event import LoginEvent, kenya_time

PAIR_WINDOW  = timedelta(minutes=5)
PAIR_LIMIT   = 5
IP_WINDOW    = timedelta(minutes=5)
IP_LIMIT     = 25
USER_WINDOW  = timedelta(minutes=15)
USER_LIMIT   = 60
RETENTION    = timedelta(days=7)


def _blocked(query, window, limit):
    """Seconds to wait if the windowed query already has `limit` entries."""
    if query.count() < limit:
        return 0
    oldest = query.order_by(LoginEvent.created_at.asc()).first()
    if not oldest or not oldest.created_at:
        return int(window.total_seconds())
    elapsed = (kenya_time() - oldest.created_at).total_seconds()
    return max(1, int(window.total_seconds() - elapsed) + 1)


def check_login(username, ip):
    """Return seconds to wait if this username/IP is over its limit, else 0."""
    now      = kenya_time()
    username = (username or "")[:50]
    ip       = (ip or "")[:64]
    failures = LoginEvent.query.filter(LoginEvent.succeeded.is_(False))

    wait = _blocked(
        failures.filter(
            LoginEvent.username == username,
            LoginEvent.ip == ip,
            LoginEvent.created_at >= now - PAIR_WINDOW,
        ),
        PAIR_WINDOW, PAIR_LIMIT,
    )
    if wait:
        return wait
    wait = _blocked(
        failures.filter(LoginEvent.ip == ip, LoginEvent.created_at >= now - IP_WINDOW),
        IP_WINDOW, IP_LIMIT,
    )
    if wait:
        return wait
    if username:
        wait = _blocked(
            failures.filter(
                LoginEvent.username == username,
                LoginEvent.created_at >= now - USER_WINDOW,
            ),
            USER_WINDOW, USER_LIMIT,
        )
        if wait:
            return wait
    return 0


def record_login(username, ip, succeeded):
    """Store the attempt; a success clears that username/IP failure streak."""
    try:
        username = (username or "")[:50]
        ip       = (ip or "")[:64]
        if succeeded:
            LoginEvent.query.filter(
                LoginEvent.username == username,
                LoginEvent.ip == ip,
                LoginEvent.succeeded.is_(False),
            ).delete(synchronize_session=False)
            LoginEvent.query.filter(
                LoginEvent.created_at < kenya_time() - RETENTION
            ).delete(synchronize_session=False)
        db.session.add(LoginEvent(
            username   = username,
            ip         = ip,
            succeeded  = bool(succeeded),
            created_at = kenya_time(),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


# ── Step-up checks (already authenticated, so in-memory is enough) ───────────
WINDOW_SECONDS = 300
STEPUP_LIMIT   = 5

_events = defaultdict(deque)
_lock = threading.Lock()


def _prune(dq, now):
    while dq and now - dq[0] >= WINDOW_SECONDS:
        dq.popleft()


def _stepup_retry(dq, now):
    if len(dq) < STEPUP_LIMIT:
        return 0
    return max(1, int(WINDOW_SECONDS - (now - dq[0])) + 1)


def check_stepup(key):
    now = time.time()
    with _lock:
        return _stepup_retry(_events[key], now)


def fail_stepup(key):
    now = time.time()
    with _lock:
        dq = _events[key]
        dq.append(now)
        _prune(dq, now)
        if len(_events) > 5000:
            for k in list(_events):
                _prune(_events[k], now)
                if not _events[k]:
                    del _events[k]


def reset_stepup(key):
    with _lock:
        _events.pop(key, None)
