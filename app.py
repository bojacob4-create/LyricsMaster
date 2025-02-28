import os
import logging
from flask import Flask, jsonify, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
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
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    """Application factory function."""
    app = Flask(__name__)

    # Initialize bot and dispatcher as globals
    app.bot = None
    app.dispatcher = None

    def initialize_bot():
        """Initialize bot if not already initialized."""
        if app.bot is None:
            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_TOKEN not found")

            app.bot = Bot(token=token)
            app.dispatcher = Dispatcher(app.bot, None, use_context=True)

            # Register handlers
            app.dispatcher.add_handler(CommandHandler("start", start_command))
            app.dispatcher.add_handler(CommandHandler("help", help_command))
            app.dispatcher.add_handler(CommandHandler("lyrics", lyrics_command))
            app.dispatcher.add_handler(CommandHandler("stats", stats_command))
            app.dispatcher.add_handler(CommandHandler("recommend", recommend_command))
            app.dispatcher.add_handler(CommandHandler("quiz", quiz_command))
            app.dispatcher.add_handler(CommandHandler("endquiz", end_quiz_command))
            app.dispatcher.add_handler(CommandHandler("translate", translate_lyrics_command))
            app.dispatcher.add_handler(CommandHandler("youtube", youtube_command))
            app.dispatcher.add_handler(CommandHandler("analyze", analyze_command))
            app.dispatcher.add_handler(CommandHandler("subscribe", subscribe_daily_command))
            app.dispatcher.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
            app.dispatcher.add_handler(CommandHandler("download", download_command))
            app.dispatcher.add_handler(CommandHandler("wiki", wiki_command))
            app.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            logger.info("Bot initialized successfully")

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            if app.bot is None:
                initialize_bot()

            # Verify bot connection
            app.bot.get_me()
            return jsonify({
                'status': 'healthy',
                'bot_running': True,
                'last_error': None
            })
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    @app.route('/setup_webhook')
    def init_webhook():
        """Initialize webhook setup."""
        try:
            if app.bot is None:
                initialize_bot()

            # Get domain from environment or headers
            replit_domain = os.environ.get('REPL_SLUG')
            repl_owner = os.environ.get('REPL_OWNER')
            if replit_domain and repl_owner:
                domain = f"{replit_domain}.{repl_owner}.repl.co"
            else:
                domain = request.headers.get('X-Replit-User-Domain', request.host)

            token = os.environ.get("TELEGRAM_TOKEN")
            webhook_url = f"https://{domain}/{token}"

            # Delete existing webhook and set new one
            app.bot.delete_webhook()
            app.bot.set_webhook(webhook_url)

            logger.info(f"Webhook set to {webhook_url}")
            return jsonify({
                'success': True,
                'webhook_url': webhook_url
            })
        except Exception as e:
            logger.error(f"Error in webhook setup: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route(f'/{os.environ.get("TELEGRAM_TOKEN")}', methods=['POST'])
    def webhook():
        """Handle incoming webhook updates from Telegram."""
        try:
            if app.bot is None:
                initialize_bot()

            logger.info("Received webhook request")

            # Get the request data
            if not request.is_json:
                logger.error("Received non-JSON request")
                return jsonify({'error': 'Request must be JSON'}), 400

            update_data = request.get_json()
            logger.debug(f"Received update data: {update_data}")

            # Process the update
            update = Update.de_json(update_data, app.bot)
            app.dispatcher.process_update(update)

            logger.info("Successfully processed webhook update")
            return 'ok'
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}")
            return jsonify({'error': str(e)}), 500

    # Initialize bot on app creation
    initialize_bot()

    return app

# Create app instance
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)