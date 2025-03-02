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

    def initialize_bot():
        """Initialize bot if not already initialized."""
        if app.updater is None:
            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_TOKEN not found")

            # Initialize updater with polling
            app.updater = Updater(token=token, use_context=True)
            dispatcher = app.updater.dispatcher

            # Register handlers
            dispatcher.add_handler(CommandHandler("start", start_command))
            dispatcher.add_handler(CommandHandler("help", help_command))
            dispatcher.add_handler(CommandHandler("lyrics", lyrics_command))
            dispatcher.add_handler(CommandHandler("stats", stats_command))
            dispatcher.add_handler(CommandHandler("recommend", recommend_command))
            dispatcher.add_handler(CommandHandler("quiz", quiz_command))
            dispatcher.add_handler(CommandHandler("endquiz", end_quiz_command))
            dispatcher.add_handler(CommandHandler("translate", translate_lyrics_command))
            dispatcher.add_handler(CommandHandler("youtube", youtube_command))
            dispatcher.add_handler(CommandHandler("analyze", analyze_command))
            dispatcher.add_handler(CommandHandler("subscribe", subscribe_daily_command))
            dispatcher.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
            dispatcher.add_handler(CommandHandler("download", download_command))
            dispatcher.add_handler(CommandHandler("wiki", wiki_command))
            dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            # Start polling in a non-blocking way
            app.updater.start_polling()
            logger.info("Bot initialized and polling started")

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            if app.updater is None:
                initialize_bot()

            bot_info = app.updater.bot.get_me()
            logger.info(f"Bot connection test successful. Bot username: {bot_info.username}")

            return jsonify({
                'status': 'healthy',
                'bot_initialized': True,
                'bot_username': bot_info.username,
                'mode': 'polling'
            })
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    # Initialize bot on app creation
    try:
        initialize_bot()
        logger.info("Bot initialized during app creation")
    except Exception as e:
        logger.error(f"Failed to initialize bot during app creation: {str(e)}")

    return app

# Create the Flask app
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)