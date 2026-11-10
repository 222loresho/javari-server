"""In-memory PIN attempt throttle.

Tracks recent failures per username, account and client IP so a 4-digit PIN
cannot be brute-forced. State is per process; the app runs a single instance.
"""
import threading
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 300
USER_LIMIT = 5
IP_LIMIT = 25

_events = defaultdict(deque)
_lock = threading.Lock()


def _prune(dq, now):
    while dq and now - dq[0] >= WINDOW_SECONDS:
        dq.popleft()


def _retry_after(dq, limit, now):
    if len(dq) < limit:
        return 0
    return max(1, int(WINDOW_SECONDS - (now - dq[0])) + 1)


def check(user_key, ip_key=None):
    """Return seconds to wait if a key is over its limit, else 0."""
    now = time.time()
    with _lock:
        if user_key:
            wait = _retry_after(_events[user_key], USER_LIMIT, now)
            if wait:
                return wait
        if ip_key:
            wait = _retry_after(_events[ip_key], IP_LIMIT, now)
            if wait:
                return wait
    return 0


def fail(*keys):
    now = time.time()
    with _lock:
        for key in keys:
            if not key:
                continue
            dq = _events[key]
            dq.append(now)
            _prune(dq, now)
        if len(_events) > 5000:
            for key in list(_events):
                _prune(_events[key], now)
                if not _events[key]:
                    del _events[key]


def reset(*keys):
    with _lock:
        for key in keys:
            if key:
                _events.pop(key, None)
