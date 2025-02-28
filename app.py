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

    # Initialize bot
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN not found")

    bot = Bot(token=token)
    dispatcher = Dispatcher(bot, None, use_context=True)

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

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            # Verify bot connection
            bot.get_me()
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

    @app.route(f'/{token}', methods=['POST'])
    def webhook():
        """Handle incoming webhook updates from Telegram."""
        try:
            update = Update.de_json(request.get_json(force=True), bot)
            dispatcher.process_update(update)
            return 'ok'
        except Exception as e:
            logger.error(f"Error processing update: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.before_first_request
    def setup_webhook():
        """Set up webhook before the first request."""
        try:
            # Get the Replit-specific domain from the request
            webhook_url = f"https://{request.host}/{token}"
            bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {str(e)}")

    return app

# Create app instance
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)