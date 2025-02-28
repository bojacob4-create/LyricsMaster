import os
import logging
import threading
from flask import Flask, jsonify
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

# Global variable to track bot thread
bot_thread = None
bot_status = {"running": False, "last_error": None}

def start_bot():
    """Start the bot in a separate thread."""
    global bot_status
    try:
        bot_main()
        bot_status["running"] = True
        bot_status["last_error"] = None
    except Exception as e:
        bot_status["running"] = False
        bot_status["last_error"] = str(e)
        logger.error(f"Bot error: {str(e)}")

@app.route('/')
@app.route('/health')
def health_check():
    """Health check endpoint that also ensures bot is running."""
    global bot_thread, bot_status

    # Start bot thread if not running
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()
        logger.info("Started new bot thread")

    status = {
        'status': 'healthy' if bot_status["running"] else 'error',
        'bot_running': bot_thread.is_alive() if bot_thread else False,
        'last_error': bot_status["last_error"]
    }
    return jsonify(status)

if __name__ == '__main__':
    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    logger.info("Initial bot thread started")

    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)