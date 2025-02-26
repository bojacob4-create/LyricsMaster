import os
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import BotCommand

from handlers import start_command, help_command, lyrics_command, translate_lyrics_command
from services.lastfm_service import get_top_tracks

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more detailed logs
)
logger = logging.getLogger(__name__)

def error_handler(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    # Send a friendly message to the user
    if update and update.message:
        update.message.reply_text(
            "🤖 Oops! I hit a snag while processing your request. Let's try that again! 🔄"
        )

def main():
    """Start the bot."""
    # Get the token from environment variable
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No token provided!")
        return

    logger.info(f"Starting bot with token: {token[:5]}...")

    try:
        # Create the Updater and pass it your bot's token
        updater = Updater(token, use_context=True)
        logger.info("Successfully created Updater")

        # Get the dispatcher to register handlers
        dp = updater.dispatcher
        logger.info("Registering command handlers...")

        # Add command handlers
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(CommandHandler("lyrics", lyrics_command))
        dp.add_handler(CommandHandler("translate", translate_lyrics_command))
        logger.info("Command handlers registered successfully")

        # Add error handler
        dp.add_error_handler(error_handler)
        logger.info("Error handler registered")

        # Set up the commands for the bot
        commands = [
            BotCommand("start", "Start your musical journey 🎵"),
            BotCommand("help", "Get help and tips 💡"),
            BotCommand("lyrics", "Find song lyrics 🎤 (format: artist - song)"),
            BotCommand("translate", "Get Arabic lyrics translation 🌍 (format: artist - song)")
        ]
        updater.bot.set_my_commands(commands)
        logger.info("Bot commands registered with Telegram")

        # Start the Bot
        logger.info("Starting polling...")
        updater.start_polling()

        # Run the bot until you press Ctrl-C
        logger.info("Bot started successfully!")
        logger.info("Available commands: /start, /help, /lyrics, /translate")
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error starting bot: {str(e)}")
        raise

if __name__ == '__main__':
    main()