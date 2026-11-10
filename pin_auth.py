import hmac

from werkzeug.security import check_password_hash, generate_password_hash

_HASH_PREFIXES = ("scrypt:", "pbkdf2:")
_DUMMY_HASH = generate_password_hash("0000")


def is_hashed(value):
    return isinstance(value, str) and value.startswith(_HASH_PREFIXES)


def hash_pin(pin):
    return generate_password_hash(pin)


def pin_matches(stored, pin):
    """Check a PIN against either a slow hash or a legacy plaintext value."""
    stored = (stored or "").strip()
    if not stored or not pin:
        return False
    if is_hashed(stored):
        try:
            return check_password_hash(stored, pin)
        except ValueError:
            return False
    return hmac.compare_digest(stored.encode(), pin.encode())


def burn_check(pin):
    """Spend the same hash time for unknown usernames so timing does not leak."""
    try:
        check_password_hash(_DUMMY_HASH, pin or "0000")
    except ValueError:
        pass
