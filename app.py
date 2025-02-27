import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting application initialization...")

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Set the secret key
app.secret_key = os.environ.get("SESSION_SECRET")

# Simple database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # Enable automatic reconnection
}

# Initialize SQLAlchemy
db.init_app(app)

with app.app_context():
    # Import models here to ensure they're registered
    import models
    # Create all tables
    db.create_all()
    logger.info("Database initialization completed successfully")