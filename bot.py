import logging
import os
import signal
import sys
import time
from datetime import datetime
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
from services.daily_song_service import send_daily_song

# Configure logging with more detail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Set to DEBUG for more detailed logs
)
logger = logging.getLogger(__name__)

# Global flags for bot status
should_stop = False
last_activity = datetime.now()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global should_stop
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    should_stop = True

def update_activity():
    """Update the last activity timestamp."""
    global last_activity
    last_activity = datetime.now()

class TelegramBotWrapper:
    def __init__(self, token):
        """Initialize the bot with retry mechanism."""
        self.token = token
        self.updater = None
        self.retry_count = 0
        self.max_retries = 10
        self.base_delay = 1  # Base delay in seconds
        self.max_delay = 300  # Maximum delay of 5 minutes
        self.start_time = None
        self.health_check_interval = 300  # 5 minutes

    def log_health_status(self):
        """Log bot health status."""
        if self.start_time:
            uptime = datetime.now() - self.start_time
            last_seen = datetime.now() - last_activity
            logger.info(
                f"Bot Health Status:\n"
                f"Uptime: {uptime}\n"
                f"Last Activity: {last_seen.seconds} seconds ago\n"
                f"Retry Count: {self.retry_count}\n"
                f"Connection Status: Active"
            )

    def setup_bot(self):
        """Set up the bot with handlers and commands."""
        try:
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30,
                    'pool_timeout': 3.0,
                    'connect_retries': 3,
                }
            )
            dp = self.updater.dispatcher

            # Register command handlers
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

            # Add message handler for quiz answers with activity tracking
            def wrapped_quiz_answer(update: Update, context: CallbackContext):
                update_activity()
                return quiz_answer(update, context)
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, wrapped_quiz_answer))

            # Add error handler
            dp.add_error_handler(self.error_handler)

            # Set commands list
            self.set_commands()

            logger.info("Bot setup completed successfully")
            self.start_time = datetime.now()
            return True

        except Exception as e:
            logger.error(f"Error in bot setup: {str(e)}", exc_info=True)
            return False

    def set_commands(self):
        """Set up bot commands with descriptions."""
        try:
            commands = [
                BotCommand("start", "Begin your musical journey 🎵"),
                BotCommand("help", "Get detailed help and tips 💡"),
                BotCommand("lyrics", "Get song lyrics with mood analysis 🎤"),
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
                BotCommand("wiki", "Get Wikipedia info about artists 📚")
            ]
            self.updater.bot.set_my_commands(commands)
            logger.info("Successfully set bot commands")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {str(e)}")

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle errors with retry logic."""
        try:
            if isinstance(context.error, NetworkError):
                logger.warning("Network error occurred, will retry connection")
                raise context.error
            elif isinstance(context.error, TimedOut):
                logger.warning("Request timed out, will retry")
                raise context.error
            elif isinstance(context.error, RetryAfter):
                logger.warning(f"Need to retry after {context.error.retry_after} seconds")
                time.sleep(context.error.retry_after)
                return
            else:
                logger.error(f"Update {update} caused error: {context.error}", exc_info=True)

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something went wrong.\n"
                    "Please try again in a moment! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")

    def health_check(self):
        """Perform periodic health checks."""
        while not should_stop:
            time.sleep(self.health_check_interval)
            self.log_health_status()

            # Check for long periods of inactivity
            if (datetime.now() - last_activity).seconds > 3600:  # 1 hour
                logger.warning("No activity detected for over an hour, checking connection...")
                try:
                    # Test the connection by getting bot info
                    self.updater.bot.get_me()
                    logger.info("Connection test successful")
                except Exception as e:
                    logger.error(f"Connection test failed: {str(e)}")
                    return False

            if should_stop:
                break

        return True

    def start(self):
        """Start the bot with retry mechanism."""
        global should_stop
        while not should_stop:
            try:
                if not self.setup_bot():
                    raise Exception("Bot setup failed")

                logger.info("Starting bot polling...")
                self.updater.start_polling(drop_pending_updates=True)
                logger.info("Bot started successfully!")

                # Reset retry count on successful connection
                self.retry_count = 0
                update_activity()

                # Start health check in the background
                import threading
                health_thread = threading.Thread(target=self.health_check)
                health_thread.daemon = True
                health_thread.start()

                # Keep the bot running
                self.updater.idle()

                # If we get here, idle() was interrupted
                if should_stop:
                    logger.info("Stopping bot gracefully...")
                    self.updater.stop()
                    break

            except Exception as e:
                if should_stop:
                    break

                self.retry_count += 1
                delay = min(self.base_delay * (2 ** self.retry_count), self.max_delay)

                logger.error(f"Bot crashed: {str(e)}", exc_info=True)
                logger.info(f"Attempting to restart in {delay} seconds... (Attempt {self.retry_count})")

                if self.retry_count > self.max_retries:
                    logger.critical("Maximum retry attempts reached. Bot is shutting down.")
                    break

                time.sleep(delay)

def main():
    """Start the bot with improved error handling and recovery."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Starting bot with automatic recovery...")
        bot = TelegramBotWrapper(token)
        bot.start()

    except Exception as e:
        logger.critical(f"Critical error during bot initialization: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()