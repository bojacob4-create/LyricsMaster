import os
import logging
import json
import signal
from flask import Flask, jsonify, request
from telegram import Bot, BotCommand
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters
from handlers import (
    start_command, help_command, lyrics_command, stats_command,
    recommend_command, quiz_command, quiz_answer, end_quiz_command,
    translate_lyrics_command, youtube_command, analyze_command,
    subscribe_daily_command, unsubscribe_daily_command,
    download_command, wiki_command, trending_command
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
    app.config['PROPAGATE_EXCEPTIONS'] = True
    app.updater = None

    def initialize_bot():
        """Initialize bot with proper cleanup."""
        try:
            # Stop any existing updater
            if app.updater and app.updater.running:
                logger.info("Stopping existing updater...")
                app.updater.stop()
                app.updater = None

            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                logger.error("TELEGRAM_TOKEN not found")
                raise ValueError("TELEGRAM_TOKEN not found")

            logger.info("Initializing new bot instance...")

            # Create updater with robust settings
            app.updater = Updater(
                token=token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30
                }
            )

            # Verify bot token
            bot_info = app.updater.bot.get_me()
            logger.info(f"Bot token verified. Username: {bot_info.username}")

            # Register handlers
            dispatcher = app.updater.dispatcher

            # Set up bot commands menu
            commands = [
                BotCommand("start", "Begin your musical journey 🎵"),
                BotCommand("help", "Get detailed help and tips 💡"),
                BotCommand("lyrics", "Get song lyrics with mood analysis 🎤"),
                BotCommand("stats", "Get detailed song statistics 📊"),
                BotCommand("recommend", "Discover similar songs 🎵"),
                BotCommand("quiz", "Play an interactive lyrics quiz 🎮"),
                BotCommand("translate", "Get Arabic lyrics translation 🌍"),
                BotCommand("youtube", "Find songs on YouTube 🎬"),
                BotCommand("analyze", "Get deep song analysis 📈"),
                BotCommand("subscribe", "Get daily song discoveries 🔔"),
                BotCommand("unsubscribe", "Stop daily updates 🔕"),
                BotCommand("wiki", "Get Wikipedia info about artists 📚"),
                BotCommand("trending", "See what's hot right now! 🔥")
            ]

            try:
                app.updater.bot.set_my_commands(commands)
                logger.info("Bot commands menu set up successfully")
            except Exception as e:
                logger.error(f"Failed to set up bot commands: {e}")

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
                ("wiki", wiki_command),
                ("trending", trending_command)
            ]

            for command, handler in handlers:
                logger.debug(f"Adding handler for /{command}")
                dispatcher.add_handler(CommandHandler(command, handler))

            # Add message handler for quiz answers
            dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            # Add error handler
            def error_handler(update, context):
                """Log errors."""
                error = context.error
                logger.error(f"Update {update} caused error: {error}")

            dispatcher.add_error_handler(error_handler)

            # Start polling
            logger.info("Starting bot polling...")
            app.updater.start_polling(drop_pending_updates=True)
            logger.info("Bot polling started successfully")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}", exc_info=True)
            if app.updater:
                try:
                    app.updater.stop()
                except:
                    pass
                app.updater = None
            return False

    @app.route('/')
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        try:
            # Initialize bot if not running
            if not app.updater or not app.updater.running:
                logger.info("Bot not running, initializing...")
                if not initialize_bot():
                    return jsonify({
                        'status': 'error',
                        'error': 'Failed to initialize bot'
                    }), 500

            # Verify bot is responsive
            bot_info = app.updater.bot.get_me()
            logger.info(f"Health check: Bot is alive. Username: {bot_info.username}")

            return jsonify({
                'status': 'healthy',
                'bot_username': bot_info.username,
                'pid': os.getpid(),
                'mode': 'polling'
            })

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

    # Initialize bot when app is created
    try:
        logger.info("Initializing bot during app creation...")
        initialize_bot()
    except Exception as e:
        logger.error(f"Initial bot setup failed: {e}", exc_info=True)

    return app

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)