import os
import logging
from flask import Flask, jsonify
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting application initialization...")

# Create Flask app with production config
app = Flask(__name__)
app.config.from_object(config['production'])
config['production'].init_app(app)

# Health check endpoints
@app.route('/')
@app.route('/health')
def health_check():
    """Basic health check endpoint."""
    status = {
        'status': 'healthy',
        'app_initialized': True,
        'service_status': 'running'
    }
    return jsonify(status), 200

@app.route('/readiness')
def readiness_check():
    """Readiness probe endpoint."""
    try:
        # Add any additional checks here
        status = {
            'status': 'ready',
            'dependencies': {
                'telegram_bot': True,
                'database': True
            }
        }
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        return jsonify({
            'status': 'not ready',
            'error': str(e)
        }), 503

logger.info("Application initialization completed")