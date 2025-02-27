import os
import logging
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting application initialization...")

class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy with the base class
db = SQLAlchemy(model_class=Base)

# Create Flask app
app = Flask(__name__)

# Get configuration
env = os.environ.get('FLASK_ENV', 'development')
logger.info(f"Loading configuration for environment: {env}")
try:
    app_config = config[env]()
    app.config.from_object(app_config)
    app_config.init_app(app)
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {str(e)}")
    raise

# Initialize the app with the extension
db.init_app(app)

# Add health check endpoint
@app.route('/health')
def health_check():
    status = {
        'database_url_exists': bool(os.environ.get('DATABASE_URL')),
        'database_configured': bool(app.config.get('SQLALCHEMY_DATABASE_URI')),
        'app_initialized': True
    }
    try:
        # Test database connection
        with app.app_context():
            db.session.execute('SELECT 1')
            status['database_connected'] = True
    except Exception as e:
        status['database_connected'] = False
        status['error'] = str(e)

    return jsonify(status)

# Create database tables
with app.app_context():
    try:
        import models
        db.create_all()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        error_msg = (
            f"Database initialization failed: {str(e)}\n"
            "Please check:\n"
            "1. DATABASE_URL is correctly set in your deployment secrets\n"
            "2. The database server is accessible\n"
            "3. The database credentials are correct"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)