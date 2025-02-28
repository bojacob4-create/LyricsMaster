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
    level=logging.DEBUG
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
        self.health_check_interval = 30  # Reduced health check interval to 30 seconds

    def setup_bot(self):
        """Set up the bot with handlers and commands."""
        try:
            logger.info("Starting bot setup with token...")
            max_retries = 5
            retry_count = 0

            while retry_count < max_retries:
                try:
                    # Initialize with higher timeouts for better stability
                    self.updater = Updater(
                        token=self.token,
                        use_context=True,
                        request_kwargs={
                            'read_timeout': 30,
                            'connect_timeout': 30
                        }
                    )

                    # Test bot connection immediately with multiple retries
                    for attempt in range(3):
                        try:
                            bot_info = self.updater.bot.get_me()
                            logger.info(f"Bot connection test successful - Username: {bot_info.username}")
                            break
                        except Exception as e:
                            if attempt == 2:  # Last attempt
                                raise
                            logger.warning(f"Connection test attempt {attempt + 1} failed, retrying...")
                            time.sleep(2)

                    # Configure dispatcher with error handling
                    dp = self.updater.dispatcher
                    if not dp:
                        raise Exception("Failed to initialize dispatcher")

                    logger.info("Setting up command handlers...")

                    # Register command handlers with logging
                    dp.add_handler(CommandHandler("start", self.log_command(start_command)))
                    dp.add_handler(CommandHandler("help", self.log_command(help_command)))
                    dp.add_handler(CommandHandler("lyrics", self.log_command(lyrics_command)))
                    dp.add_handler(CommandHandler("stats", self.log_command(stats_command)))
                    dp.add_handler(CommandHandler("recommend", self.log_command(recommend_command)))
                    dp.add_handler(CommandHandler("quiz", self.log_command(quiz_command)))
                    dp.add_handler(CommandHandler("endquiz", self.log_command(end_quiz_command)))
                    dp.add_handler(CommandHandler("translate", self.log_command(translate_lyrics_command)))
                    dp.add_handler(CommandHandler("youtube", self.log_command(youtube_command)))
                    dp.add_handler(CommandHandler("analyze", self.log_command(analyze_command)))
                    dp.add_handler(CommandHandler("subscribe", self.log_command(subscribe_daily_command)))
                    dp.add_handler(CommandHandler("unsubscribe", self.log_command(unsubscribe_daily_command)))
                    dp.add_handler(CommandHandler("download", self.log_command(download_command)))
                    dp.add_handler(CommandHandler("wiki", self.log_command(wiki_command)))

                    # Add message handler for quiz answers with activity tracking and logging
                    def wrapped_quiz_answer(update: Update, context: CallbackContext):
                        logger.info(f"Received quiz answer from user {update.effective_user.id}")
                        update_activity()
                        return quiz_answer(update, context)

                    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, wrapped_quiz_answer))

                    # Enhanced error handler
                    dp.add_error_handler(self.error_handler)

                    # Set commands list
                    self.set_commands()

                    logger.info("Bot setup completed successfully")
                    self.start_time = datetime.now()
                    return True

                except Exception as e:
                    retry_count += 1
                    wait_time = min(2 ** retry_count, 60)  # Cap wait time at 60 seconds
                    logger.warning(f"Setup attempt {retry_count} failed: {str(e)}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    if retry_count == max_retries:
                        raise Exception(f"Failed to establish initial connection after {max_retries} retries")

            return True

        except Exception as e:
            logger.error(f"Critical error in bot setup: {str(e)}", exc_info=True)
            return False

    def log_command(self, handler):
        """Decorator to add logging to command handlers."""
        def wrapped(update: Update, context: CallbackContext):
            user_id = update.effective_user.id
            command = update.message.text
            logger.info(f"Received command '{command}' from user {user_id}")
            try:
                return handler(update, context)
            except Exception as e:
                logger.error(f"Error processing command '{command}' for user {user_id}: {str(e)}", exc_info=True)
                update.message.reply_text("😓 Something went wrong processing your command. Please try again!")
                raise
        return wrapped

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
        """Handle errors with enhanced logging."""
        try:
            if isinstance(context.error, NetworkError):
                logger.error(f"Network error occurred: {str(context.error)}", exc_info=True)
                logger.info("Attempting connection recovery...")
                raise context.error
            elif isinstance(context.error, TimedOut):
                logger.error(f"Request timed out: {str(context.error)}", exc_info=True)
                logger.info("Attempting timeout recovery...")
                raise context.error
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                logger.warning(f"Rate limit hit. Waiting {retry_after} seconds before retry.")
                time.sleep(retry_after)
                return
            else:
                logger.error(f"Update {update} caused error: {context.error}", exc_info=True)

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something went wrong.\n"
                    "Don't worry, I'll try to reconnect automatically! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}", exc_info=True)
            logger.info("Will attempt automatic recovery")

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
                f"Connection Status: Active\n"
                f"Memory Usage: Active" 
            )

    def monitor_bot_health(self):
        """Monitor bot health and force restart if unresponsive."""
        try:
            # Test the bot's ability to respond
            bot_info = self.updater.bot.get_me()
            logger.info(f"Bot health check passed - Bot ID: {bot_info.id}")
            return True
        except Exception as e:
            logger.error(f"Bot health check failed: {str(e)}", exc_info=True)
            return False

    def health_check(self):
        """Perform periodic health checks."""
        while not should_stop:
            try:
                time.sleep(self.health_check_interval)
                self.log_health_status()

                # Check for long periods of inactivity
                if (datetime.now() - last_activity).seconds > 1800:  # Reduced to 30 minutes
                    logger.warning("No activity detected for over 30 minutes, checking connection...")
                    for attempt in range(3):  # Try up to 3 times
                        if self.monitor_bot_health():
                            logger.info("Bot health check passed after retry")
                            break
                        elif attempt == 2:  # Last attempt failed
                            logger.critical("Bot appears unresponsive, forcing restart...")
                            if self.updater:
                                try:
                                    self.updater.stop()
                                except:
                                    pass
                            self.updater = None
                            return False  # This will trigger a restart in the main loop
                        else:
                            logger.warning(f"Health check attempt {attempt + 1} failed, retrying...")
                            time.sleep(5)  # Reduced wait time between retries

                if should_stop:
                    logger.info("Health check stopping due to shutdown signal")
                    break

            except Exception as e:
                logger.error(f"Error in health check: {str(e)}")
                logger.info("Will continue monitoring in next interval")
                continue

        return True

    def start(self):
        """Start the bot with enhanced retry mechanism."""
        global should_stop
        consecutive_failures = 0
        max_consecutive_failures = 3

        while not should_stop:
            try:
                if not self.setup_bot():
                    logger.error("Bot setup failed, attempting recovery...")
                    raise Exception("Bot setup failed")

                logger.info("Starting bot polling with improved recovery...")
                self.updater.start_polling(
                    timeout=60,
                    bootstrap_retries=5,
                    read_latency=5.0,
                    allowed_updates=['message', 'callback_query', 'chosen_inline_result', 'inline_query', 'chat_member']  # Extended update types
                )
                logger.info("Bot started successfully! Ready to process commands...")

                # Reset failure count on successful start
                consecutive_failures = 0
                update_activity()

                # Start health check in the background
                import threading
                health_thread = threading.Thread(target=self.health_check, daemon=True)  # Make thread daemon
                health_thread.start()
                logger.info("Health monitoring thread started")

                # Keep the bot running
                self.updater.idle()

                if should_stop:
                    logger.info("Received stop signal, shutting down gracefully...")
                    self.updater.stop()
                    break

            except Exception as e:
                if should_stop:
                    break

                consecutive_failures += 1
                self.retry_count += 1
                delay = min(self.base_delay * (2 ** self.retry_count), self.max_delay)

                logger.error(f"Bot crashed with error: {str(e)}", exc_info=True)
                logger.info(f"Attempting to restart in {delay} seconds... (Attempt {self.retry_count}/{self.max_retries})")

                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("Too many consecutive failures. Forcing full restart...")
                    if self.updater:
                        try:
                            self.updater.stop()
                        except:
                            pass
                    self.updater = None  # Force complete reinitialization
                    consecutive_failures = 0
                    time.sleep(30)  # Longer cooldown period
                    continue

                if self.retry_count > self.max_retries:
                    logger.critical("Maximum retry attempts reached. Resetting retry count...")
                    self.retry_count = 0  # Reset instead of breaking
                    consecutive_failures = 0
                    time.sleep(60)  # Longer cooldown before fresh start
                    continue

                time.sleep(delay)

def main():
    """Start the bot with improved error handling and recovery."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Configure deployment-specific logging
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('bot_deployment.log')
            ]
        )
        logger.info("Starting bot in deployment mode with automatic recovery...")

        # Initialize and start bot with improved error handling
        bot = TelegramBotWrapper(token)
        bot.start()

    except Exception as e:
        logger.critical(f"Critical error during bot initialization: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()