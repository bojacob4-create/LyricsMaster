import os
import logging
import json
from flask import Flask, jsonify, request
from telegram import Update, Bot
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters
from handlers import (
    start_command, help_command, lyrics_command, stats_command,
    recommend_command, quiz_command, quiz_answer, end_quiz_command,
    translate_lyrics_command, youtube_command, analyze_command,
    subscribe_daily_command, unsubscribe_daily_command,
    download_command, wiki_command
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

LOCK_FILE = "/tmp/telegram_bot.lock"

def create_app():
    """Application factory function."""
    app = Flask(__name__)
    app.updater = None

    def is_bot_running():
        """Check if bot instance is already running."""
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    pid = int(f.read().strip())
                try:
                    os.kill(pid, 0)  # Check if process exists
                    return True
                except OSError:
                    # Process not running, remove stale lock file
                    os.remove(LOCK_FILE)
            except (ValueError, OSError):
                pass
        return False

    def create_lock_file():
        """Create lock file with current process ID."""
        try:
            with open(LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            logger.info("Created lock file")
        except OSError as e:
            logger.error(f"Failed to create lock file: {e}")
            raise

    def cleanup_bot():
        """Clean up any existing bot instances."""
        try:
            if app.updater:
                logger.info("Stopping existing bot instance...")
                app.updater.stop()
                app.updater = None
                logger.info("Bot instance stopped")

            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
                logger.info("Lock file removed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def initialize_bot():
        """Initialize bot if not already running."""
        try:
            if is_bot_running():
                raise RuntimeError("Another bot instance is already running")

            cleanup_bot()  # Clean up any existing instances
            create_lock_file()  # Create lock file for this instance

            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_TOKEN not found")

            logger.info("Creating new bot instance...")
            app.updater = Updater(token=token, use_context=True)
            dispatcher = app.updater.dispatcher

            # Add command handlers with logging
            handlers = [
                ("start", start_command),
                ("help", help_command),
                ("lyrics", lyrics_command),
                ("stats", stats_command),
                ("recommend", recommend_command),
                ("quiz", quiz_command),
                ("endquiz", end_quiz_command),
                ("translate", translate_lyrics_command),
                ("youtube", youtube_command),
                ("analyze", analyze_command),
                ("subscribe", subscribe_daily_command),
                ("unsubscribe", unsubscribe_daily_command),
                ("download", download_command),
                ("wiki", wiki_command)
            ]

            for command, handler in handlers:
                logger.debug(f"Adding handler for /{command}")
                dispatcher.add_handler(CommandHandler(command, handler))

            dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))
            logger.debug("Added text message handler")

            def error_handler(update, context):
                """Log errors."""
                error = context.error
                logger.error(f"Update {update} caused error: {error}")
                logger.error(f"Full error details: {json.dumps(str(error), indent=2)}")

            dispatcher.add_error_handler(error_handler)
            logger.debug("Added error handler")

            # Start polling with clean start
            logger.info("Starting bot polling...")
            app.updater.start_polling(drop_pending_updates=True)

            # Verify bot
            bot_info = app.updater.bot.get_me()
            logger.info(f"Bot initialized successfully. Username: {bot_info.username}")

            return True
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}", exc_info=True)
            cleanup_bot()  # Clean up on failure
            raise

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            if app.updater is None:
                logger.info("No bot instance found, initializing...")
                initialize_bot()

            if not app.updater or not app.updater.running:
                return jsonify({
                    'status': 'error',
                    'error': 'Bot not running'
                }), 500

            bot_info = app.updater.bot.get_me()
            return jsonify({
                'status': 'healthy',
                'bot_username': bot_info.username,
                'mode': 'polling',
                'is_running': True
            })
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    return app

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)