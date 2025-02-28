import logging
import os
import sys
import time
import signal
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
    start_command, help_command, lyrics_command, stats_command,
    recommend_command, quiz_command, quiz_answer, end_quiz_command,
    translate_lyrics_command, youtube_command, analyze_command,
    subscribe_daily_command, unsubscribe_daily_command,
    download_command, wiki_command
)

# Configure logging with both console and file handlers
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

class TelegramBotWorker:
    def __init__(self, token):
        self.token = token
        self.updater = None
        self.retry_count = 0
        self.max_retries = 5
        self.retry_delay = 60  # seconds
        self.last_keepalive = time.time()
        self.keepalive_interval = 30  # seconds
        self.running = True

        # Log bot startup
        logger.info("Bot worker initialized with monitor logging")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False
        if self.updater:
            self.updater.stop()

    def setup_commands(self):
        """Set up bot commands menu."""
        try:
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
                BotCommand("wiki", "Get Wikipedia info about artists 📚")
            ]
            self.updater.bot.set_my_commands(commands)
            logger.info("Bot commands menu set up successfully")
        except Exception as e:
            logger.error(f"Failed to set up bot commands: {str(e)}")

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle bot errors."""
        try:
            if isinstance(context.error, NetworkError):
                logger.warning(f"Network error occurred: {str(context.error)}")
                self.handle_connection_error()
                return
            elif isinstance(context.error, TimedOut):
                logger.warning("Request timed out")
                self.handle_connection_error()
                return
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                logger.warning(f"Rate limit hit. Waiting {retry_after} seconds")
                time.sleep(retry_after)
                return
            else:
                logger.error(f"Update {update} caused error: {context.error}")

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Something went wrong. Please try again in a moment! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")

    def handle_connection_error(self):
        """Handle connection errors with exponential backoff."""
        wait_time = min(300, self.retry_delay * (2 ** self.retry_count))  # Max 5 minutes
        logger.info(f"Connection error, waiting {wait_time} seconds before retry...")
        time.sleep(wait_time)
        self.retry_count += 1

    def keepalive(self):
        """Perform keepalive tasks."""
        current_time = time.time()
        if current_time - self.last_keepalive >= self.keepalive_interval:
            try:
                # Verify bot connection
                self.updater.bot.get_me()
                logger.debug("Keepalive check successful")
                self.last_keepalive = current_time
                self.retry_count = 0  # Reset retry count on successful keepalive
            except Exception as e:
                logger.warning(f"Keepalive check failed: {str(e)}")
                self.handle_connection_error()

    def initialize(self):
        """Initialize the bot with handlers."""
        try:
            # Create the Updater with persistent retry settings
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30,
                    'pool_timeout': 3600,  # 1 hour pool timeout
                }
            )

            # Get the dispatcher
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

            # Add message handler for quiz answers
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

            # Add error handler
            dp.add_error_handler(self.error_handler)

            # Set up commands menu
            self.setup_commands()

            logger.info("Bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize bot: {str(e)}")
            return False

    def run(self):
        """Run the bot with automatic reconnection and keepalive."""
        while self.running:
            try:
                if not self.initialize():
                    if self.retry_count >= self.max_retries:
                        logger.error("Max retries reached. Exiting...")
                        sys.exit(1)

                    self.retry_count += 1
                    wait_time = self.retry_delay * (2 ** (self.retry_count - 1))
                    logger.info(f"Retrying initialization in {wait_time} seconds... (Attempt {self.retry_count}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue

                # Reset retry count on successful initialization
                self.retry_count = 0
                self.last_keepalive = time.time()

                logger.info("Starting bot polling...")

                # Start polling in a non-blocking way
                self.updater.start_polling(
                    drop_pending_updates=True,
                    timeout=30,
                    read_latency=1.0,
                    allowed_updates=['message', 'callback_query']
                )

                logger.info("Bot is running successfully")

                # Main loop with keepalive checks
                while self.running and self.updater.running:
                    self.keepalive()
                    time.sleep(1)  # Prevent CPU overuse

            except Exception as e:
                logger.error(f"Bot crashed: {str(e)}")
                if self.updater:
                    try:
                        self.updater.stop()
                    except:
                        pass
                self.updater = None

                if self.retry_count >= self.max_retries:
                    logger.error("Max retries reached. Exiting...")
                    sys.exit(1)

                self.retry_count += 1
                wait_time = self.retry_delay * (2 ** (self.retry_count - 1))
                logger.info(f"Restarting bot in {wait_time} seconds... (Attempt {self.retry_count}/{self.max_retries})")
                time.sleep(wait_time)

        logger.info("Bot shutdown complete")

def main():
    """Entry point for the bot worker."""
    try:
        # Get token from environment
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN not found in environment variables")

        # Create and run bot
        bot_worker = TelegramBotWorker(token)
        bot_worker.run()

    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()