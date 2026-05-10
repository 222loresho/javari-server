from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from flask import Flask
from flask_cors import CORS
from extensions import db, jwt
import os
from datetime import timedelta

app = Flask(__name__)

CORS(app,
     origins=[
         "https://222loresho.github.io",
         "http://localhost:5173",
         "http://127.0.0.1:5173",
         "http://localhost:3000",
     ],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     supports_credentials=True)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET", "09333f71c3fd95637e321ff2f35feccf08d1e9a7c505f7d215863210b6feae49")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "postgresql://postgres.brkvmeleudpontlxmmir:0OHz1aGVi2fye7EA@aws-1-eu-west-1.pooler.supabase.com:6543/postgres")
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

from routes.auth import auth_bp
from routes.products import products_bp
from routes.categories import categories_bp
from routes.sales import sales_bp
from routes.orders import orders_bp
from routes.users import users_bp
from routes.reports import reports_bp

app.register_blueprint(auth_bp,       url_prefix='/api/auth')
app.register_blueprint(products_bp,   url_prefix='/api/products')
app.register_blueprint(categories_bp, url_prefix='/api/categories')
app.register_blueprint(sales_bp,      url_prefix='/api/sales')
app.register_blueprint(orders_bp,     url_prefix='/api/orders')
app.register_blueprint(users_bp,      url_prefix='/api/users')
app.register_blueprint(reports_bp,    url_prefix='/api/reports')

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5001)