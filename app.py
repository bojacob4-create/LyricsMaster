import os
import logging
from flask import Flask, jsonify, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, Updater
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

def create_app():
    """Application factory function."""
    app = Flask(__name__)
    app.updater = None

    def cleanup_bot():
        """Clean up any existing bot instances."""
        try:
            if app.updater:
                logger.info("Stopping existing bot instance...")
                app.updater.stop()
                app.updater = None
                logger.info("Existing bot instance stopped")
        except Exception as e:
            logger.error(f"Error during bot cleanup: {str(e)}")

    def initialize_bot():
        """Initialize bot if not already initialized."""
        try:
            # Clean up any existing instances first
            cleanup_bot()

            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                logger.error("TELEGRAM_TOKEN not found in environment")
                raise ValueError("TELEGRAM_TOKEN not found")

            logger.info("Initializing new bot instance...")
            app.updater = Updater(token=token, use_context=True)
            dispatcher = app.updater.dispatcher

            # Register command handlers
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
                logger.debug(f"Adding handler for command: /{command}")
                dispatcher.add_handler(CommandHandler(command, handler))

            # Add message handler for quiz answers
            dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            # Add error handler
            def error_handler(update, context):
                """Log any errors."""
                logger.error(f"Error handling update {update}: {context.error}")

            dispatcher.add_error_handler(error_handler)

            # Start polling
            logger.info("Starting bot polling...")
            app.updater.start_polling(clean=True)

            # Verify bot is working
            bot_info = app.updater.bot.get_me()
            logger.info(f"Bot initialized successfully. Username: {bot_info.username}")

        except Exception as e:
            logger.error(f"Failed to initialize bot: {str(e)}", exc_info=True)
            raise

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            if app.updater is None or not app.updater.running:
                logger.info("Bot not running, initializing now...")
                initialize_bot()

            bot_info = app.updater.bot.get_me()
            logger.info(f"Health check: Bot is alive. Username: {bot_info.username}")

            return jsonify({
                'status': 'healthy',
                'bot_initialized': True,
                'bot_username': bot_info.username,
                'mode': 'polling'
            })
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    # Initialize bot on app creation
    try:
        initialize_bot()
        logger.info("Bot initialized during app creation")
    except Exception as e:
        logger.error(f"Failed to initialize bot during app creation: {str(e)}", exc_info=True)

    return app

# Create app instance
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)