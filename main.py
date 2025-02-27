from app import app
from bot import main
import logging
import threading
import requests
import time
import os

# Configure root logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def keep_alive():
    """Keep the Replit instance alive by pinging the web server."""
    replit_url = os.environ.get('REPLIT_DB_URL', '').split('//')[1].split(':')[0]
    if replit_url:
        ping_url = f"https://{replit_url}/"
    else:
        ping_url = "http://0.0.0.0:5000/"

    while True:
        try:
            # Try both the Replit URL and local URL
            try:
                requests.get(ping_url)
            except:
                requests.get("http://0.0.0.0:5000/")
            logger.debug("Keep-alive ping successful")
            time.sleep(60)  # Ping every minute instead of 3 minutes
        except Exception as e:
            logger.error(f"Keep-alive ping failed: {str(e)}")
            time.sleep(30)  # Reduced retry interval to 30 seconds

def run_flask():
    """Run Flask app in production mode"""
    try:
        logger.info("Starting Flask server...")
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        logger.info("Starting application...")

        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Start keep-alive thread
        keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
        keep_alive_thread.start()

        # Start the bot
        main()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise