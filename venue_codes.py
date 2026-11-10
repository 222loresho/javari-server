def venue_code_for(name, used):
    """Derive a short, unique venue code from the venue name."""
    base = "".join(ch for ch in (name or "").upper() if ch.isalnum())[:3] or "VEN"
    base = base.ljust(3, "X")
    code, n = base, 1
    while code in used:
        n += 1
        code = f"{base}{n}"
    return code
