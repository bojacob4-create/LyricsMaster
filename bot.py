import logging
import os
from telegram import Update, BotCommand
from telegram.ext import (
    CallbackContext, 
    Updater,
    CommandHandler,
    MessageHandler,
    Filters
)
from telegram.error import TelegramError
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
from datetime import time

# Configure logging with optimized settings
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Set to INFO for better performance
)
logger = logging.getLogger(__name__)

def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.error(f'Update "{update}" caused error "{context.error}"')
    try:
        if update and update.effective_message:
            update.effective_message.reply_text(
                "😓 Something went wrong. Please try again! 🔄"
            )
    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}")

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        # Initialize the bot with optimized settings
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30,
                'read_latency': 1.0,
                'connect_retries': 3
            }
        )
        dp = updater.dispatcher

        # Register command handlers efficiently
        handlers = [
            ("start", start_command),
            ("help", help_command),
            ("lyrics", lyrics_command),
            ("stats", stats_command),
            ("recommend", recommend_command),
            ("quiz", quiz_command),
            ("endquiz", end_quiz_command),
            ("translate", translate_lyrics_command),
            ("youtube", youtube_command),
            ("analyze", analyze_command),
            ("subscribe", subscribe_daily_command),
            ("unsubscribe", unsubscribe_daily_command),
            ("download", download_command),
            ("wiki", wiki_command)
        ]

        # Add handlers efficiently
        for command, handler in handlers:
            dp.add_handler(CommandHandler(command, handler))

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Add error handler
        dp.add_error_handler(error_handler)

        # Set commands list
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

        try:
            updater.bot.set_my_commands(commands)
        except Exception as e:
            logger.warning(f"Failed to set bot commands: {str(e)}")
            # Continue anyway as this is not critical

        # Start the Bot with optimized settings
        logger.info("Starting bot...")
        updater.start_polling(
            drop_pending_updates=True,
            timeout=30,
            read_latency=1.0,
            clean=True,
            bootstrap_retries=3,
            allowed_updates=['message', 'callback_query']  # Only listen for needed updates
        )
        logger.info("Bot is running!")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()