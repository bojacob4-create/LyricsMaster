import os
import logging
from flask import Flask, jsonify

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting application initialization...")

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key-for-development")

# Add health check endpoint
@app.route('/health')
def health_check():
    status = {
        'app_initialized': True,
        'service_status': 'running'
    }
    return jsonify(status)

logger.info("Application initialization completed")