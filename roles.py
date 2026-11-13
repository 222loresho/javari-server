"""Role gates shared by the API routes. Super admins pass every gate."""
from flask import jsonify

from tenant import current_user

CASHIER_ROLES = ("admin", "manager", "cashier")
REPORT_ROLES  = ("admin", "manager", "super_admin")


def require(*roles):
    user = current_user()
    if user is None:
        return None, (jsonify({"error": "Account is inactive"}), 401)
    if user.role != "super_admin" and user.role not in roles:
        return None, (jsonify({"error": "You do not have permission to do this"}), 403)
    return user, None
