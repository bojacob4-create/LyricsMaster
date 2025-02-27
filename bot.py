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

# Configure logging with more detail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.error(f'Update "{update}" caused error "{context.error}"', exc_info=True)
    try:
        if update and update.effective_message:
            update.effective_message.reply_text(
                "😓 Oops! Something went wrong.\n"
                "Please try again in a moment! 🔄"
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

        logger.info("Starting bot initialization...")

        # Initialize the bot
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30
            }
        )
        dp = updater.dispatcher
        logger.debug("Created updater and dispatcher")

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
        logger.debug("Registered all command handlers")

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Add error handler
        dp.add_error_handler(error_handler)

        # Set commands list with detailed descriptions
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
            logger.info("Successfully set bot commands")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {str(e)}")

        # Start the Bot
        logger.info("Starting bot polling...")
        updater.start_polling(drop_pending_updates=True)
        logger.info("Bot started successfully!")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error during bot initialization: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()