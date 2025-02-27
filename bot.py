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
        self.max_retries = 3
        self.base_delay = 1
        self.max_delay = 15  # Maximum 15 seconds delay between retries
        self.last_activity = datetime.now()
        self.ACTIVITY_TIMEOUT = 60  # Force restart if no activity for 60 seconds
        self.connection_check_thread = None
        self.should_stop = False

    def setup_bot(self):
        """Set up the bot with error handling."""
        try:
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 10,  # More aggressive timeouts
                    'connect_timeout': 10
                }
            )
            dp = self.updater.dispatcher

            # Register handlers
            dp.add_handler(CommandHandler("start", self.wrapped_handler(start_command)))
            dp.add_handler(CommandHandler("help", self.wrapped_handler(help_command)))
            dp.add_handler(CommandHandler("lyrics", self.wrapped_handler(lyrics_command)))
            dp.add_handler(CommandHandler("stats", self.wrapped_handler(stats_command)))
            dp.add_handler(CommandHandler("recommend", self.wrapped_handler(recommend_command)))
            dp.add_handler(CommandHandler("quiz", self.wrapped_handler(quiz_command)))
            dp.add_handler(CommandHandler("endquiz", self.wrapped_handler(end_quiz_command)))
            dp.add_handler(CommandHandler("translate", self.wrapped_handler(translate_lyrics_command)))
            dp.add_handler(CommandHandler("youtube", self.wrapped_handler(youtube_command)))
            dp.add_handler(CommandHandler("analyze", self.wrapped_handler(analyze_command)))
            dp.add_handler(CommandHandler("subscribe", self.wrapped_handler(subscribe_daily_command)))
            dp.add_handler(CommandHandler("unsubscribe", self.wrapped_handler(unsubscribe_daily_command)))
            dp.add_handler(CommandHandler("download", self.wrapped_handler(download_command)))
            dp.add_handler(CommandHandler("wiki", self.wrapped_handler(wiki_command)))
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.wrapped_handler(quiz_answer)))
            dp.add_error_handler(self.error_handler)

            # Set commands
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

            logger.info("Bot initialization completed successfully")
            print("Bot initialization completed successfully")  # Explicit stdout message
            return True

        except Exception as e:
            logger.error(f"Error in bot setup: {str(e)}")
            return False

    def wrapped_handler(self, handler):
        """Wrapper for command handlers to track activity."""
        def wrapper(update, context):
            try:
                self.last_activity = datetime.now()
                return handler(update, context)
            except Exception as e:
                logger.error(f"Handler error: {str(e)}")
                raise
        return wrapper

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle errors with retry logic."""
        try:
            if isinstance(context.error, (NetworkError, TimedOut)):
                logger.warning(f"Network/Timeout error: {str(context.error)}")
                self.force_restart()
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                logger.warning(f"Rate limit hit, waiting {retry_after} seconds")
                time.sleep(retry_after)
            else:
                logger.error(f"Error: {context.error}")

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something went wrong.\n"
                    "Don't worry, I'll reconnect automatically! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")
            self.force_restart()

    def check_connection(self):
        """Monitor bot connection and activity."""
        while not self.should_stop:
            try:
                time.sleep(5)  # Check every 5 seconds

                # Check for inactivity
                if (datetime.now() - self.last_activity).total_seconds() > self.ACTIVITY_TIMEOUT:
                    logger.warning("Bot inactive for too long, forcing restart")
                    self.force_restart()
                    continue

                # Verify connection with a simple API call
                self.updater.bot.get_me()

            except Exception as e:
                logger.error(f"Connection check failed: {str(e)}")
                self.force_restart()

    def force_restart(self):
        """Force a bot restart."""
        logger.info("Forcing bot restart...")
        try:
            if self.updater:
                self.updater.stop()
            self.setup_bot()
            self.updater.start_polling(drop_pending_updates=True)
            logger.info("Bot restarted successfully")
        except Exception as e:
            logger.error(f"Error during force restart: {str(e)}")
            raise

    def start(self):
        """Start the bot with enhanced recovery."""
        import threading

        while not self.should_stop:
            try:
                if not self.setup_bot():
                    raise Exception("Bot setup failed")

                logger.info("Starting bot...")
                self.updater.start_polling(drop_pending_updates=True)
                self.retry_count = 0
                self.last_activity = datetime.now()

                # Start connection monitoring in a separate thread
                self.connection_check_thread = threading.Thread(target=self.check_connection)
                self.connection_check_thread.daemon = True
                self.connection_check_thread.start()

                # Signal that the bot is ready
                logger.info("Bot started successfully")
                print("Bot started successfully")  # Explicit stdout message

                self.updater.idle()

            except KeyboardInterrupt:
                logger.info("Received shutdown signal, stopping...")
                self.should_stop = True
                if self.updater:
                    self.updater.stop()
                break

            except Exception as e:
                self.retry_count += 1
                delay = min(self.base_delay * (2 ** self.retry_count), self.max_delay)

                logger.error(f"Bot error: {str(e)}")
                logger.info(f"Retrying in {delay} seconds... (Attempt {self.retry_count}/{self.max_retries})")

                if self.retry_count > self.max_retries:
                    logger.error("Maximum retry attempts reached")
                    break

                time.sleep(delay)

def main():
    try:
        # Check for required token
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("TELEGRAM_TOKEN not found!")
            raise ValueError("TELEGRAM_TOKEN environment variable not set")

        # Set up signal handlers
        signal.signal(signal.SIGTERM, lambda signo, frame: sys.exit(0))
        signal.signal(signal.SIGINT, lambda signo, frame: sys.exit(0))

        logger.info("Starting bot process...")
        bot = TelegramBotWrapper(token)
        bot.start()

    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()