from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from flask import Flask, jsonify
from flask_cors import CORS
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
