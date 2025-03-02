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
    level=logging.DEBUG,  # Set to DEBUG for more detailed logs
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

            # Test bot connection
            bot_info = app.bot.get_me()
            logger.info(f"Bot connection test successful. Bot username: {bot_info.username}")

            return jsonify({
                'status': 'healthy',
                'bot_initialized': True,
                'bot_username': bot_info.username
            })
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    @app.route('/setup_webhook')
    def setup_webhook():
        """Set up webhook for Telegram bot."""
        try:
            if app.bot is None:
                initialize_bot()

            # Get Replit environment variables
            repl_slug = os.environ.get('REPL_SLUG')
            if not repl_slug:
                logger.error("REPL_SLUG environment variable not found")
                return jsonify({
                    'success': False,
                    'error': 'REPL_SLUG environment variable not found'
                }), 500

            # Use basic Replit domain format
            webhook_url = f"https://{repl_slug}.repl.co/{os.environ.get('TELEGRAM_TOKEN')}"
            logger.info(f"Setting webhook to URL: {webhook_url}")

            try:
                # Remove existing webhook
                app.bot.delete_webhook()
                logger.info("Deleted existing webhook")

                # Set new webhook with basic configuration
                success = app.bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True
                )

                if not success:
                    logger.error("Failed to set webhook")
                    return jsonify({
                        'success': False,
                        'error': 'Failed to set webhook'
                    }), 500

                # Get webhook info for verification
                webhook_info = app.bot.get_webhook_info()
                logger.info(f"Webhook info: {webhook_info.url}")

                if webhook_info.last_error_date:
                    logger.warning(f"Last webhook error: {webhook_info.last_error_message}")

                return jsonify({
                    'success': True,
                    'webhook_url': webhook_url,
                    'webhook_info': {
                        'url': webhook_info.url,
                        'last_error': webhook_info.last_error_message if webhook_info.last_error_date else None
                    }
                })

            except Exception as webhook_error:
                logger.error(f"Webhook setup failed: {str(webhook_error)}")
                return jsonify({
                    'success': False,
                    'error': str(webhook_error)
                }), 500

        except Exception as e:
            logger.error(f"Error in setup_webhook: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route(f'/{os.environ.get("TELEGRAM_TOKEN")}', methods=['POST'])
    def webhook():
        """Handle incoming webhook updates from Telegram."""
        try:
            if app.bot is None:
                initialize_bot()

            if not request.is_json:
                logger.error("Received non-JSON request")
                return jsonify({'error': 'Request must be JSON'}), 400

            # Log incoming update
            update_data = request.get_json()
            logger.debug(f"Received update: {update_data}")

            update = Update.de_json(update_data, app.bot)
            app.dispatcher.process_update(update)

            return '', 200

        except Exception as e:
            logger.error(f"Error processing webhook update: {str(e)}")
            return jsonify({'error': str(e)}), 500

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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)