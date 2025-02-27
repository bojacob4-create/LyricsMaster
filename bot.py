import logging
import os
import threading
from flask import Flask
from telegram import Update, BotCommand
from telegram.ext import CallbackContext, CommandHandler, Updater, MessageHandler, Filters
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

# Configure logging with more detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Temporarily set to DEBUG for more detailed logs
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

def error_handler(update, context):
    """Log Errors caused by Updates."""
    logger.error(f'Update "{update}" caused error "{context.error}"')
    logger.error(f"Full error details: {str(context.error)}")
    if update and update.message:
        update.message.reply_text(
            "🤖 Oops! I hit a snag while processing your request. Let's try that again! 🔄"
        )

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        logger.info("Starting bot initialization...")

        # Initialize the bot
        logger.debug("Creating Updater instance...")
        updater = Updater(token, use_context=True)
        dp = updater.dispatcher
        logger.info("Bot updater and dispatcher initialized successfully")

        # Register command handlers
        logger.debug("Registering command handlers...")
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(CommandHandler("lyrics", lyrics_command))
        dp.add_handler(CommandHandler("stats", stats_command))
        dp.add_handler(CommandHandler("recommend", recommend_command))
        dp.add_handler(CommandHandler("quiz", quiz_command))
        dp.add_handler(CommandHandler("endquiz", end_quiz_command))
        dp.add_handler(CommandHandler("translate", translate_lyrics_command))
        dp.add_handler(CommandHandler("youtube", youtube_command))
        dp.add_handler(CommandHandler("analyze", analyze_command))
        dp.add_handler(CommandHandler("subscribe", subscribe_daily_command))
        dp.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
        dp.add_handler(CommandHandler("download", download_command))
        logger.info("Command handlers registered successfully")

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Add error handler
        dp.add_error_handler(error_handler)

        # Schedule daily song job
        logger.debug("Setting up daily song job...")
        job_queue = updater.job_queue
        job_queue.run_daily(
            send_daily_song,
            time=time(hour=12, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6)
        )
        logger.info("Daily song job scheduled successfully")

        # Set commands list
        logger.debug("Setting up bot commands...")
        commands = [
            BotCommand("start", "Start your musical journey 🎵"),
            BotCommand("help", "Get help and tips 💡"),
            BotCommand("lyrics", "Find song lyrics 🎤 (format: artist - song)"),
            BotCommand("stats", "Get song statistics 📊 (format: artist - song)"),
            BotCommand("recommend", "Get song recommendations 🎵 (format: artist - song)"),
            BotCommand("quiz", "Start a fun lyrics quiz game 🎮"),
            BotCommand("endquiz", "End the current quiz game 🎲"),
            BotCommand("translate", "Get Arabic lyrics translation 🌍 (format: artist - song)"),
            BotCommand("subscribe", "Get a daily song with analysis 📅"),
            BotCommand("unsubscribe", "Stop receiving daily songs 🔕"),
            BotCommand("youtube", "Get YouTube link for song 🎬 (format: artist - song)"),
            BotCommand("analyze", "Get detailed song analysis 📊 (format: artist - song)"),
            BotCommand("download", "Download YouTube video 🎬 (format: /download video_url)")
        ]
        updater.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully")

        # Start the Flask app in a separate thread first
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("Flask web server started on port 5000")

        # Start the Bot
        logger.info("Starting bot polling...")
        updater.start_polling()
        logger.info("Bot is running successfully!")
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error during bot initialization: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()