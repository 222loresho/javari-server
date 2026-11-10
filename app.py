from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from werkzeug.middleware.proxy_fix import ProxyFix
from extensions import db, jwt
from datetime import timedelta

def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. For local development copy .env.example to .env; "
            f"for hosting, set it in the service's environment variables."
        )
    return value

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

default_origins = [
    "https://222loresho.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
extra_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

CORS(app,
     origins=default_origins + extra_origins,
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     supports_credentials=True)

jwt_secret = required_env("JWT_SECRET")
if len(jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters long.")

app.config["JWT_SECRET_KEY"] = jwt_secret
app.config["SQLALCHEMY_DATABASE_URI"] = required_env("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)

db.init_app(app)
jwt.init_app(app)

from models.user import User
from models.category import Category
from models.product import Product
from models.sale import Sale, SaleItem
from models.order import Order, OrderItem
from models.market import Market

from sqlalchemy import inspect, text
from venue_codes import venue_code_for
from pin_auth import hash_pin, is_hashed

def ensure_schema():
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        if "users" not in tables:
            return
        additions = [
            ("users",      "manager_id", "INTEGER"),
            ("products",   "image_url",  "VARCHAR(500)"),
            ("users",      "market_id",  "INTEGER"),
            ("categories", "market_id",  "INTEGER"),
            ("products",   "market_id",  "INTEGER"),
            ("sales",      "market_id",  "INTEGER"),
            ("orders",     "market_id",  "INTEGER"),
            ("markets",    "code",       "VARCHAR(12)"),
            ("users",      "pin_length", "INTEGER"),
        ]
        for table, column, ddl in additions:
            if table not in tables:
                continue
            columns = {c["name"] for c in inspect(db.engine).get_columns(table)}
            if column in columns:
                continue
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            app.logger.info("Added %s.%s column", table, column)
        ensure_venue_codes()
        ensure_username_scope()
        ensure_pin_hashes()

def ensure_venue_codes():
    """Give every venue a short login code, e.g. Freetown → FRE."""
    used = {m.code.upper() for m in Market.query.all() if m.code}
    changed = False
    for m in Market.query.order_by(Market.id).all():
        if m.code:
            continue
        m.code = venue_code_for(m.name, used)
        used.add(m.code)
        changed = True
        app.logger.info("Assigned venue code %s to %s", m.code, m.name)
    if changed:
        db.session.commit()
    if db.engine.dialect.name == "postgresql":
        try:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_markets_code "
                    "ON markets (upper(code)) WHERE code IS NOT NULL"
                ))
        except Exception:
            app.logger.exception("Could not enforce venue code uniqueness")

def ensure_username_scope():
    """Usernames are unique per venue (plus one platform namespace), not globally."""
    if "users" not in set(inspect(db.engine).get_table_names()):
        return
    if db.engine.dialect.name != "postgresql":
        return
    try:
        with db.engine.begin() as conn:
            legacy = conn.execute(text(
                "SELECT c.conname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE t.relname = 'users' AND c.contype = 'u' "
                "AND pg_get_constraintdef(c.oid) = 'UNIQUE (username)'"
            )).fetchall()
            for (name,) in legacy:
                conn.execute(text(f'ALTER TABLE users DROP CONSTRAINT IF EXISTS "{name}"'))
                app.logger.info("Dropped global username constraint %s", name)
            conn.execute(text(
                'CREATE UNIQUE INDEX IF NOT EXISTS ux_users_venue_username '
                'ON users (market_id, lower(username)) WHERE market_id IS NOT NULL'
            ))
            conn.execute(text(
                'CREATE UNIQUE INDEX IF NOT EXISTS ux_users_platform_username '
                'ON users (lower(username)) WHERE market_id IS NULL'
            ))
    except Exception:
        app.logger.exception("Could not scope usernames per venue")

def ensure_pin_hashes():
    """Replace plaintext PINs with slow hashes; the column must be wide enough."""
    if db.engine.dialect.name == "postgresql":
        try:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ALTER COLUMN pin TYPE VARCHAR(255)"))
        except Exception:
            app.logger.exception("Could not widen users.pin; keeping plaintext PINs")
            return
    changed = False
    for u in User.query.all():
        stored = (u.pin or "").strip()
        if not stored:
            continue
        hashed = is_hashed(stored)
        if u.pin_length is None:
            u.pin_length = 4 if hashed else len(stored)
            changed = True
        if hashed:
            continue
        u.pin = hash_pin(stored)
        changed = True
    if changed:
        db.session.commit()
        app.logger.info("Stored PINs are now hashed")

ensure_schema()

@app.before_request
def reject_inactive_tokens():
    """A signed-in account must still exist and be active on every request."""
    if request.method == "OPTIONS" or not request.headers.get("Authorization"):
        return None
    try:
        verify_jwt_in_request(optional=True)
    except Exception:
        return None
    ident = get_jwt_identity()
    if ident is None:
        return None
    user = User.query.get(ident)
    if not user or not user.active:
        return jsonify({"error": "This account is inactive. Ask your admin."}), 401
    return None

@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

def sync_menu_catalog():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if not {"products", "categories"} <= tables:
            return
        from menu_catalog import sync_menu
        added = sync_menu()
        if added:
            app.logger.info("Synced %d menu products into the POS catalog", added)

sync_menu_catalog()

from routes.auth import auth_bp
from routes.products import products_bp
from routes.categories import categories_bp
from routes.sales import sales_bp
from routes.orders import orders_bp
from routes.users import users_bp
from routes.reports import reports_bp
from routes.superadmin import superadmin_bp

app.register_blueprint(auth_bp,       url_prefix='/api/auth')
app.register_blueprint(products_bp,   url_prefix='/api/products')
app.register_blueprint(categories_bp, url_prefix='/api/categories')
app.register_blueprint(sales_bp,      url_prefix='/api/sales')
app.register_blueprint(orders_bp,     url_prefix='/api/orders')
app.register_blueprint(users_bp,      url_prefix='/api/users')
app.register_blueprint(reports_bp,    url_prefix='/api/reports')
app.register_blueprint(superadmin_bp,  url_prefix='/api/superadmin')

@app.get("/api/health")
def health():
    return jsonify(status="ok")

if __name__ == '__main__':
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5001")),
    )
