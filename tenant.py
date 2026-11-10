from flask_jwt_extended import get_jwt_identity
from sqlalchemy import false
from models.user import User


def current_user():
    ident = get_jwt_identity()
    if not ident:
        return None
    user = User.query.get(ident)
    if not user or not user.active:
        return None
    return user


def scoped(model, user=None):
    """Query limited to the signed-in user's venue; super admins see everything."""
    user = user if user is not None else current_user()
    if user is None:
        return model.query.filter(false())
    if user.role == "super_admin":
        return model.query
    if user.market_id is None:
        return model.query.filter(false())
    return model.query.filter(model.market_id == user.market_id)


def in_venue(obj, user=None):
    user = user if user is not None else current_user()
    if user is None:
        return False
    if user.role == "super_admin":
        return True
    return user.market_id is not None and obj.market_id == user.market_id
