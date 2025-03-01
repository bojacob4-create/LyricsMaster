import logging
import os
import time
import sys
import socket
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import NetworkError, Unauthorized, TimedOut
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
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

def is_port_in_use(port):
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def error_handler(update: Update, context: CallbackContext):
    """Handle errors in the dispatcher."""
    try:
        if isinstance(context.error, Unauthorized):
            logger.error("Unauthorized - Invalid token")
        elif isinstance(context.error, NetworkError):
            logger.error(f"Network error: {context.error}")
        elif isinstance(context.error, TimedOut):
            logger.error(f"Request timed out: {context.error}")
        else:
            logger.error(f"Error handling update {update}: {context.error}")

        if update and update.effective_message:
            update.effective_message.reply_text(
                "😓 Something went wrong. Please try again in a moment! 🔄"
            )
    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}")

def main():
    """Start the bot."""
    retry_count = 0
    max_retries = 3
    retry_delay = 5  # seconds

    # Check if another instance is running
    if is_port_in_use(8443):  # Use Telegram's recommended port
        logger.error("Another bot instance is already running")
        sys.exit(1)

    while retry_count < max_retries:
        try:
            # Get token from environment
            token = os.environ.get("TELEGRAM_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_TOKEN not found")

            logger.info("Initializing bot...")

            # Create the Updater with request timeouts
            updater = Updater(
                token=token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30
                }
            )
            dp = updater.dispatcher

            # Add error handler
            dp.add_error_handler(error_handler)

            # Register commands
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
            dp.add_handler(CommandHandler("wiki", wiki_command))

            # Add message handler for quiz answers
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            logger.info("Starting bot...")
            # Start polling with minimal settings to avoid conflicts
            updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=['message']
            )
            logger.info("Bot started successfully!")

            # Run the bot until the process stops
            updater.idle()
            break  # If we get here, bot started successfully

        except Exception as e:
            logger.error(f"Error starting bot (attempt {retry_count + 1}/{max_retries}): {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Exiting.")
                raise

if __name__ == '__main__':
    main()