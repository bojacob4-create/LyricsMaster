import logging
import os
import sys
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

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBotWrapper:
    def __init__(self, token):
        self.token = token
        self.updater = None

    def setup_bot(self):
        try:
            # Initialize with minimal settings
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 10,
                    'connect_timeout': 10
                }
            )

            dp = self.updater.dispatcher
            if not dp:
                raise Exception("Failed to initialize dispatcher")

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

            # Set up error handler
            dp.add_error_handler(self.error_handler)

            # Set commands
            self.set_commands()

            return True

        except Exception as e:
            logger.error(f"Error in bot setup: {str(e)}")
            return False

    def set_commands(self):
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
        except Exception as e:
            logger.error(f"Failed to set bot commands: {str(e)}")

    def error_handler(self, update: Update, context: CallbackContext):
        try:
            if isinstance(context.error, (NetworkError, TimedOut)):
                # Just log and let polling handle reconnection
                logger.warning(f"Connection error: {str(context.error)}")
                return
            elif isinstance(context.error, RetryAfter):
                logger.warning(f"Rate limit hit. Waiting {context.error.retry_after} seconds.")
                return
            else:
                logger.error(f"Update {update} caused error: {context.error}")

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Oops! Something went wrong.\n"
                    "Please try again in a moment! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")

    def start(self):
        """Start the bot with minimal settings."""
        while True:
            try:
                if not self.setup_bot():
                    logger.error("Bot setup failed, retrying...")
                    continue

                logger.info("Starting bot polling...")
                self.updater.start_polling(
                    timeout=10,
                    read_latency=1.0,
                    drop_pending_updates=True,
                    allowed_updates=['message', 'callback_query']
                )

                logger.info("Bot is running...")
                self.updater.idle()

            except Exception as e:
                logger.error(f"Bot encountered an error: {str(e)}")
                if self.updater:
                    try:
                        self.updater.stop()
                    except:
                        pass
                    self.updater = None
                continue

def main():
    """Start the bot."""
    try:
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        bot = TelegramBotWrapper(token)
        bot.start()

    except Exception as e:
        logger.critical(f"Critical error in bot initialization: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()