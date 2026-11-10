from models.product import Product
from tenant import in_venue

MAX_QUANTITY = 999


def build_lines(user, raw_items):
    """Turn a client cart into trusted lines priced from the database.

    Returns (lines, total, error). Every line is a dict with product, name,
    quantity, price and subtotal; the client's prices and totals are ignored.
    """
    if not isinstance(raw_items, list) or not raw_items:
        return None, None, "Cart is empty"
    merged = {}
    for item in raw_items:
        if not isinstance(item, dict):
            return None, None, "Invalid cart item"
        try:
            product_id = int(item.get("product_id"))
        except (TypeError, ValueError):
            return None, None, "Invalid product in cart"
        try:
            quantity = int(item.get("quantity"))
        except (TypeError, ValueError):
            return None, None, "Quantity must be a whole number"
        if quantity < 1 or quantity > MAX_QUANTITY:
            return None, None, f"Quantity must be between 1 and {MAX_QUANTITY}"
        product = Product.query.get(product_id)
        if not product or not in_venue(product, user):
            return None, None, "Unknown product in cart"
        if product_id in merged:
            merged[product_id]["quantity"] += quantity
        else:
            merged[product_id] = {"product": product, "quantity": quantity}

    lines = []
    total = 0.0
    for entry in merged.values():
        price    = float(entry["product"].price or 0)
        subtotal = round(price * entry["quantity"], 2)
        total    = round(total + subtotal, 2)
        lines.append({
            "product":  entry["product"],
            "name":     entry["product"].name,
            "quantity": entry["quantity"],
            "price":    price,
            "subtotal": subtotal,
        })
    return lines, total, None
