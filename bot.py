import os
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

from handlers import start_command, help_command, lyrics_command, top_tracks_command, translate_lyrics_command

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def error_handler(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    """Start the bot."""
    # Get the token from environment variable
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No token provided!")
        return

    # Create the Updater and pass it your bot's token
    updater = Updater(token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("lyrics", lyrics_command))
    dp.add_handler(CommandHandler("toptracks", top_tracks_command))
    dp.add_handler(CommandHandler("translate", translate_lyrics_command))

    # Add error handler
    dp.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C
    logger.info("Bot started successfully!")
    updater.idle()

if __name__ == '__main__':
    main()