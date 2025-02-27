from app import app
from bot import main
import logging
import threading
import requests
import time
import os
from datetime import datetime

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

    backoff = 1  # Initial backoff in seconds
    max_backoff = 30  # Maximum backoff in seconds
    while True:
        try:
            # Try both the Replit URL and local URL
            try:
                response = requests.get(ping_url, timeout=5)
                if response.status_code == 200:
                    logger.debug(f"Keep-alive ping successful at {datetime.now()}")
                    backoff = 1  # Reset backoff on success
                else:
                    logger.warning(f"Keep-alive ping returned status {response.status_code}")
                    raise requests.RequestException("Non-200 status code")
            except:
                response = requests.get("http://0.0.0.0:5000/", timeout=5)
                if response.status_code == 200:
                    logger.debug("Local keep-alive ping successful")
                    backoff = 1  # Reset backoff on success
                else:
                    raise requests.RequestException("Local ping failed")

            time.sleep(5)  # Ping every 5 seconds when successful

        except Exception as e:
            logger.error(f"Keep-alive ping failed: {str(e)}")
            # Exponential backoff with maximum limit
            sleep_time = min(backoff, max_backoff)
            logger.info(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)
            backoff = min(backoff * 2, max_backoff)  # Double the backoff time, but don't exceed max

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

        # Start Flask in a separate thread as a secondary process
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Start keep-alive thread
        keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
        keep_alive_thread.start()

        # Start the bot as the primary process
        main()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise