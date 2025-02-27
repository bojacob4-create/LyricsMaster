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
        """Set up the bot with error handling."""
        try:
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30
                }
            )
            dp = self.updater.dispatcher

            # Register handlers
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
            dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))
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

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle errors with retry logic."""
        try:
            if isinstance(context.error, NetworkError):
                logger.warning(f"Network error: {str(context.error)}")
                raise context.error
            elif isinstance(context.error, TimedOut):
                logger.warning(f"Timeout error: {str(context.error)}")
                raise context.error
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                logger.warning(f"Rate limit hit, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return
            else:
                logger.error(f"Error: {context.error}")

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something went wrong.\n"
                    "Don't worry, I'll reconnect automatically! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")

    def start(self):
        """Start the bot with recovery."""
        while True:
            try:
                if not self.setup_bot():
                    raise Exception("Bot setup failed")

                logger.info("Starting bot...")
                self.updater.start_polling(drop_pending_updates=True)
                self.is_running = True
                self.retry_count = 0
                self.last_restart = datetime.now()

                # Signal that the bot is ready
                logger.info("Bot started successfully")
                print("Bot started successfully")  # Explicit stdout message

                self.updater.idle()

            except KeyboardInterrupt:
                logger.info("Received shutdown signal, stopping...")
                if self.updater:
                    self.updater.stop()
                break

            except Exception as e:
                self.is_running = False
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