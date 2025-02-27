import os
import logging
from telegram import Update, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Configure basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> None:
    """Basic start command handler."""
    logger.info(f"Start command received from user {update.effective_user.id}")
    update.message.reply_text('Hello! I am your music bot. 🎵')

def echo(update: Update, context: CallbackContext) -> None:
    """Echo all messages."""
    logger.info(f"Message received: {update.message.text}")
    update.message.reply_text(f"You said: {update.message.text}")

def main() -> None:
    """Start the bot."""
    # Get the token from environment variable
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("No token found!")
        return

    logger.info("Starting bot initialization...")

    try:
        # Create the Updater
        updater = Updater(token)

        # Get the dispatcher
        dispatcher = updater.dispatcher

        # Test connection
        me = updater.bot.get_me()
        logger.info(f"Bot connected successfully as @{me.username}")

        # Add command and message handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

        # Start polling
        logger.info("Starting polling...")
        updater.start_polling(poll_interval=1, timeout=30, clean=True)

        # Run the bot until Ctrl+C
        logger.info("Bot is running. Press Ctrl-C to stop.")
        updater.idle()

    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)

if __name__ == '__main__':
    main()