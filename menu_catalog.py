import re

from extensions import db
from models.category import Category
from models.product import Product

# Customer menu (qr-menu) items that are not yet on the POS, grouped by category.
# Synonyms of products that already exist in the POS are intentionally omitted:
# Crunchy Slim Fries, Masala Fries, Poussin Fries, Samosas, Beef Sausages,
# Margarita, Long Island Iced Tea.
MENU_CATALOG = [
    ("Chips and sides", [
        ("Garlic Fries", 400),
        ("Pepper Fries", 400),
        ("Mashed Potatoes", 400),
        ("Potato Wedges", 400),
        ("Saute Potatoes", 400),
        ("Maru Bhajia", 400),
        ("Roast Potatoes", 400),
        ("Ugali", 100),
        ("Vegetable Rice", 200),
        ("Plain Rice", 320),
        ("Matoke", 300),
    ]),
    ("Bitings", [
        ("Fish Fingers", 400),
        ("Chicken Nuggets", 300),
        ("2 Choma Sausages and Fries", 400),
        ("Chilli Beef Strips", 320),
    ]),
    ("Mains & Grills", [
        ("BBQ and Bacon Burger", 400),
        ("Butter Chicken", 400),
        ("Paneer Butter Masala", 400),
        ("Sweet and Sour Chicken", 400),
        ("Chicken Tikka", 400),
        ("Chicken Wings", 800),
        ("Grilled Beef 1kg", 1000),
        ("Grilled Beef 1/2kg", 650),
        ("Goat Choma 1kg", 1400),
        ("Goat Choma 1/2kg", 700),
        ("Grilled Chicken Full", 1400),
        ("1/2 BBQ Chicken", 700),
        ("Kienyeji Chicken Choma Full", 1800),
        ("Beef Dry Fry 1kg", 1550),
        ("Chicken Dry Fry Full", 1600),
        ("Dry Fried Chicken Half", 850),
        ("Fish & Ugali", 700),
        ("Chicken & Rice", 600),
        ("Beef & Rice", 650),
    ]),
    ("Soups", [
        ("Chicken Soup", 300),
        ("Beef Soup", 300),
        ("Goat Soup", 350),
        ("Mushroom Soup", 300),
        ("Vegetable Soup", 250),
    ]),
    ("Juices", [
        ("Carrot Juice", 350),
        ("Pineapple Juice", 300),
        ("Berry Blast Antioxidant", 380),
        ("Detoxifying Green Juice", 320),
        ("Cleansing Green Elixir With Sugarcane Juice", 320),
    ]),
    ("Hot Drinks", [
        ("Espresso", 200),
        ("Coffee with Milk", 250),
        ("Black Tea", 150),
        ("Purple Tea", 180),
        ("White Tea", 850),
    ]),
    ("Cocktail", [
        ("Dawa", 850),
        ("Mojito", 650),
        ("Strawberry Daiquiri", 700),
        ("Pina Colada", 750),
        ("Aperol Spritz", 850),
        ("Passion Mojito", 850),
    ]),
]


def _norm(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower().replace("&", " and ")).strip()


def sync_menu():
    """Insert customer-menu items that are missing from the POS catalog.

    Idempotent: matches on normalized existing names, so it can run on every
    startup without creating duplicates or overwriting admin edits.
    """
    existing = {_norm(p.name) for p in Product.query.all()}
    categories = {_norm(c.name): c for c in Category.query.all()}
    added = 0

    for category_name, items in MENU_CATALOG:
        category = categories.get(_norm(category_name))
        if category is None:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()
            categories[_norm(category_name)] = category

        for name, price in items:
            if _norm(name) in existing:
                continue
            db.session.add(Product(name=name, price=price, stock=100, category_id=category.id))
            existing.add(_norm(name))
            added += 1

    db.session.commit()
    return added
