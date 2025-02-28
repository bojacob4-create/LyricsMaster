import os
import logging
import threading
import atexit
from flask import Flask, jsonify
from telegram.ext import Updater
from main import main as bot_main

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Global variables for bot management
updater = None
bot_thread = None
bot_status = {"running": False, "last_error": None, "health_check_fails": 0}

def start_bot():
    """Start the bot in a separate thread."""
    global updater, bot_status
    try:
        logger.info("Starting bot thread...")
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN not found")

        updater = Updater(token, use_context=True)
        bot_main()  # This will set up handlers and start polling
        bot_status["running"] = True
        bot_status["last_error"] = None
        bot_status["health_check_fails"] = 0
    except Exception as e:
        bot_status["running"] = False
        bot_status["last_error"] = str(e)
        logger.error(f"Bot error: {str(e)}")

def cleanup_bot():
    """Cleanup function to handle bot thread shutdown."""
    global bot_thread, updater, bot_status
    try:
        if updater:
            logger.info("Stopping updater...")
            updater.stop()
        if bot_thread and bot_thread.is_alive():
            logger.info("Shutting down bot thread...")
            bot_status["running"] = False
            bot_thread.join(timeout=5)
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

# Register the cleanup function
atexit.register(cleanup_bot)

@app.route('/')
@app.route('/health')
def health_check():
    """Health check endpoint that also ensures bot is running."""
    global bot_thread, bot_status, updater

    try:
        # Check if bot thread needs to be started
        if bot_thread is None or not bot_thread.is_alive():
            bot_thread = threading.Thread(target=start_bot, daemon=True)
            bot_thread.start()
            logger.info("Started new bot thread")

        # Verify bot connection
        if updater and updater.bot:
            try:
                updater.bot.get_me()
                bot_status["health_check_fails"] = 0
            except Exception as e:
                bot_status["health_check_fails"] += 1
                logger.warning(f"Bot connection check failed: {str(e)}")

                # If too many health checks fail, force restart
                if bot_status["health_check_fails"] >= 3:
                    logger.warning("Too many health check failures, forcing restart...")
                    cleanup_bot()
                    bot_thread = None
                    return health_check()

        status = {
            'status': 'healthy' if bot_status["running"] else 'error',
            'bot_running': bot_thread.is_alive() if bot_thread else False,
            'health_checks_failed': bot_status["health_check_fails"],
            'last_error': bot_status["last_error"]
        }

        return jsonify(status)
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    logger.info("Initial bot thread started")

    # Run Flask app with gunicorn settings
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)