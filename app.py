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

            return jsonify({
                'status': 'healthy',
                'bot_initialized': app.bot is not None,
                'last_error': None
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

            # Use proper Replit domain
            repl_id = os.environ.get('REPL_ID')
            repl_slug = os.environ.get('REPL_SLUG')
            repl_owner = os.environ.get('REPL_OWNER')

            if not all([repl_id, repl_slug, repl_owner]):
                logger.error("Missing required Replit environment variables")
                return jsonify({
                    'success': False,
                    'error': 'Missing required Replit environment variables'
                }), 500

            # Use the full qualified Replit domain
            webhook_url = f"https://{repl_slug}.{repl_owner}.repl.co/{os.environ.get('TELEGRAM_TOKEN')}"
            logger.info(f"Setting webhook to URL: {webhook_url}")

            try:
                # Delete existing webhook first
                app.bot.delete_webhook()
                logger.info("Successfully deleted existing webhook")

                # Set new webhook with correct configuration
                success = app.bot.set_webhook(
                    url=webhook_url,
                    max_connections=40,
                    allowed_updates=['message', 'callback_query']
                )

                if not success:
                    raise ValueError("Failed to set webhook")

                # Get webhook info for verification
                webhook_info = app.bot.get_webhook_info()
                logger.info(f"Webhook info after setup: {webhook_info.url}")

                if webhook_info.last_error_date:
                    logger.warning(f"Last webhook error: {webhook_info.last_error_message}")

                return jsonify({
                    'success': True,
                    'webhook_url': webhook_url,
                    'webhook_info': {
                        'url': webhook_info.url,
                        'has_custom_certificate': webhook_info.has_custom_certificate,
                        'pending_update_count': webhook_info.pending_update_count,
                        'last_error_date': webhook_info.last_error_date,
                        'last_error_message': webhook_info.last_error_message if hasattr(webhook_info, 'last_error_message') else None
                    }
                })

            except Exception as webhook_error:
                logger.error(f"Webhook setup failed: {str(webhook_error)}")
                return jsonify({
                    'success': False,
                    'error': f'Webhook setup failed: {str(webhook_error)}'
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
                return jsonify({'error': 'Request must be JSON'}), 400

            update = Update.de_json(request.get_json(), app.bot)
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