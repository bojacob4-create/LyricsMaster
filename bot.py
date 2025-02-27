import logging
import os
import threading
from flask import Flask
from telegram import Update, BotCommand
from telegram.ext import (
    CallbackContext, CommandHandler, Updater, MessageHandler, 
    Filters, TypeHandler
)
from telegram.error import (
    TelegramError, Unauthorized, BadRequest, 
    TimedOut, NetworkError
)
from datetime import time
from handlers import (
    start_command,
    help_command,
    lyrics_command,
    stats_command,
    recommend_command,
    quiz_command,
    quiz_answer,
    end_quiz_command,
    translate_lyrics_command,
    youtube_command,
    analyze_command,
    download_command,
    subscribe_daily_command,
    unsubscribe_daily_command,
    send_daily_song
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    """Health check endpoint"""
    return "Telegram Bot is running!", 200

def run_flask():
    """Run Flask app"""
    try:
        logger.info("Starting Flask server...")
        flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {str(e)}")

def error_handler(update: Update, context: CallbackContext):
    """Handle errors in the bot."""
    try:
        if isinstance(context.error, Unauthorized):
            # User has blocked the bot
            logger.warning(f"User {update.effective_user.id if update else 'Unknown'} has blocked the bot")
            return

        if isinstance(context.error, BadRequest):
            # Handle malformed requests
            logger.error(f"Bad Request: {context.error}")
            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something wasn't quite right with that request.\n"
                    "Please try again or use /help for guidance! 🔄"
                )
            return

        if isinstance(context.error, TimedOut):
            # Handle timeouts
            logger.warning(f"Request timed out: {context.error}")
            if update and update.effective_message:
                update.effective_message.reply_text(
                    "⏳ Request timed out. Please try again! 🔄"
                )
            return

        if isinstance(context.error, NetworkError):
            # Handle network errors
            logger.error(f"Network error occurred: {context.error}")
            if update and update.effective_message:
                update.effective_message.reply_text(
                    "📶 Network issues detected. Please try again in a moment! 🔄"
                )
            return

        # Log the error before handling
        logger.error(f"Update {update} caused error {context.error}", exc_info=True)

        # Send generic error message to user
        if update and update.effective_message:
            update.effective_message.reply_text(
                "🤖 Oops! I hit a snag while processing your request.\n"
                "Let's try that again! 🔄\n\n"
                "If the problem persists, try using /help for guidance."
            )

    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}", exc_info=True)

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        logger.info("Starting bot initialization...")

        # Initialize the bot with improved settings for stability
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30
            }
        )
        dp = updater.dispatcher

        # Register command handlers
        command_handlers = [
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("lyrics", lyrics_command),
            CommandHandler("stats", stats_command),
            CommandHandler("recommend", recommend_command),
            CommandHandler("quiz", quiz_command),
            CommandHandler("endquiz", end_quiz_command),
            CommandHandler("translate", translate_lyrics_command),
            CommandHandler("youtube", youtube_command),
            CommandHandler("analyze", analyze_command),
            CommandHandler("subscribe", subscribe_daily_command),
            CommandHandler("unsubscribe", unsubscribe_daily_command),
            CommandHandler("download", download_command),
        ]

        for handler in command_handlers:
            dp.add_handler(handler)
            logger.debug(f"Registered handler for command: {handler.command}")

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Add error handler
        dp.add_error_handler(error_handler)

        # Schedule daily song job
        job_queue = updater.job_queue
        job_queue.run_daily(
            send_daily_song,
            time=time(hour=12, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6)
        )

        # Set commands list with detailed descriptions
        commands = [
            BotCommand("start", "Begin your musical journey 🎵"),
            BotCommand("help", "Get detailed help and tips 💡"),
            BotCommand("lyrics", "Find song lyrics with mood analysis 🎤"),
            BotCommand("stats", "Get detailed song statistics 📊"),
            BotCommand("recommend", "Discover similar songs 🎵"),
            BotCommand("quiz", "Play an interactive lyrics quiz 🎮"),
            BotCommand("endquiz", "End the current quiz game 🎲"),
            BotCommand("translate", "Get Arabic lyrics translation 🌍"),
            BotCommand("youtube", "Find songs on YouTube 🎬"),
            BotCommand("analyze", "Get deep song analysis 📈"),
            BotCommand("download", "Download YouTube videos 📥"),
            BotCommand("subscribe", "Get daily song discoveries 📅"),
            BotCommand("unsubscribe", "Stop daily song updates 🔕"),
        ]
        updater.bot.set_my_commands(commands)

        # Start the Flask app in a separate thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        # Add periodic connection check
        def monitor_connection(context: CallbackContext):
            """Monitor bot connection state."""
            try:
                if not updater.running:
                    logger.warning("Bot connection lost, attempting to reconnect...")
                    updater.start_polling(
                        timeout=30,
                        read_latency=5.0,
                        drop_pending_updates=True,
                        allowed_updates=['message', 'callback_query'],
                        bootstrap_retries=3
                    )
                    logger.info("Bot reconnected successfully")
            except Exception as e:
                logger.error(f"Connection check failed: {str(e)}")

        # Run connection monitoring every 5 minutes
        job_queue.run_repeating(monitor_connection, interval=300, first=300)

        # Start the Bot with improved settings for stability
        logger.info("Starting bot polling...")
        updater.start_polling(
            timeout=30,
            read_latency=5.0,
            drop_pending_updates=True,
            allowed_updates=['message', 'callback_query'],  # Only process these update types
            bootstrap_retries=3,  # Number of retries for initial connection
        )

        logger.info("Bot is running successfully!")
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error during bot initialization: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()