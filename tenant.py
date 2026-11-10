from flask_jwt_extended import get_jwt_identity
from models.user import User


def current_user():
    ident = get_jwt_identity()
    return User.query.get(ident) if ident else None


def scoped(model, user=None):
    """Query limited to the signed-in user's venue; super admins see everything."""
    user = user or current_user()
    if user is None or user.role == "super_admin":
        return model.query
    return model.query.filter(model.market_id == user.market_id)


def in_venue(obj, user=None):
    user = user or current_user()
    if user is None:
        return False
    if user.role == "super_admin":
        return True
    return obj.market_id == user.market_id
