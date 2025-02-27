from app import app
from handlers import main as bot_main
import logging
import os

# Configure root logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_flask():
    """Run Flask app in production mode"""
    try:
        logger.info("Starting Flask server...")
        # Use port 5001 for Flask to avoid conflict with Telegram bot
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        logger.info("Starting application...")

        # Start the bot as the primary process on port 5000
        bot_main()

    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise