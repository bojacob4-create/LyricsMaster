import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import (
    CallbackContext,
    Updater,
    CommandHandler,
    MessageHandler,
    Filters
)
from telegram.error import (
    TelegramError,
    NetworkError,
    TimedOut,
    RetryAfter
)
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
    subscribe_daily_command,
    unsubscribe_daily_command,
    download_command,
    wiki_command
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

class TelegramBotWrapper:
    def __init__(self, token):
        self.token = token
        self.updater = None
        self.retry_count = 0
        self.max_retries = 5
        self.base_delay = 1
        self.max_delay = 60
        self.last_restart = datetime.now()
        self.RESTART_AFTER = timedelta(hours=12)
        self.is_running = False

    def setup_bot(self):
        """Set up the bot with handlers and commands."""
        try:
            logger.info("Setting up bot with token...")
            self.updater = Updater(token=self.token, use_context=True)
            dp = self.updater.dispatcher

            # Test connection
            bot_info = self.updater.bot.get_me()
            logger.info(f"Bot connected successfully. Username: @{bot_info.username}")

            # Register command handlers
            logger.info("Registering command handlers...")
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
            dp.add_handler(CommandHandler("download", download_command))
            dp.add_handler(CommandHandler("subscribe", subscribe_daily_command))
            dp.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
            dp.add_handler(CommandHandler("wiki", wiki_command))

            # Add message handler for quiz answers
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            # Add error handler
            dp.add_error_handler(self.error_handler)
            logger.info("Command handlers registered successfully")

            # Set commands list
            commands = [
                BotCommand("start", "Begin your musical journey 🎵"),
                BotCommand("help", "Get detailed help and tips 💡"),
                BotCommand("lyrics", "Get song lyrics 🎵 (format: artist - song)"),
                BotCommand("stats", "Get song statistics 📊 (format: artist - song)"),
                BotCommand("recommend", "Get song recommendations 🎵 (format: artist - song)"),
                BotCommand("quiz", "Start a lyrics quiz game 🎮"),
                BotCommand("endquiz", "End the current quiz game"),
                BotCommand("translate", "Get Arabic translation of lyrics 🌍 (format: artist - song)"),
                BotCommand("youtube", "Get YouTube link for song 🎬 (format: artist - song)"),
                BotCommand("analyze", "Get detailed song analysis 📊 (format: artist - song)"),
                BotCommand("download", "Download YouTube video 🎬 (format: /download video_url)"),
                BotCommand("subscribe", "Subscribe to daily song discovery 🎶"),
                BotCommand("unsubscribe", "Unsubscribe from daily song discovery 👋"),
                BotCommand("wiki", "Get Wikipedia info about artists 📚")
            ]
            self.updater.bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")

            return True

        except Exception as e:
            logger.error(f"Error in bot setup: {str(e)}", exc_info=True)
            return False

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle errors."""
        logger.error(f"Error occurred: {context.error}")
        try:
            raise context.error
        except NetworkError:
            logger.error("Network error occurred")
        except TelegramError:
            logger.error("Telegram API error occurred")
        except Exception as e:
            logger.error(f"Other error occurred: {str(e)}")

        if update and update.effective_message:
            update.effective_message.reply_text(
                "😓 Oops! Something went wrong.\n"
                "Please try again in a moment! 🔄"
            )

    def start(self):
        """Start the bot."""
        try:
            if not self.setup_bot():
                raise Exception("Bot setup failed")

            logger.info("Starting bot polling...")
            self.updater.start_polling()
            logger.info("Bot started successfully!")

            self.updater.idle()

        except Exception as e:
            logger.error(f"Error starting bot: {str(e)}", exc_info=True)
            raise


def signal_handler(sig, frame):
    logger.info(f"Received signal {sig}, exiting gracefully...")
    sys.exit(0)


def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        logger.info("Bot initialization starting...")
        logger.info("Token validation successful")

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Starting bot...")
        bot = TelegramBotWrapper(token)

        # Add more detailed logging
        logger.info("Starting bot wrapper...")
        bot.start()

    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    logger.info("Bot script starting...")
    main()