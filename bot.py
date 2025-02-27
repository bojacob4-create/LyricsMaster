import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    try:
        user = update.effective_user
        logger.info(f"Start command received from user {user.id}")
        update.message.reply_text(
            f'👋 Hi {user.first_name}! I am your music bot!'
        )
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}", exc_info=True)

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    try:
        logger.info(f"Help command received from user {update.effective_user.id}")
        update.message.reply_text('Send /start to test the bot!')
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}", exc_info=True)

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)

def main() -> None:
    """Start the bot."""
    try:
        # Get token from environment
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("TELEGRAM_TOKEN not found in environment variables")
            return

        logger.info("Starting bot initialization...")

        # Create updater
        updater = Updater(token, use_context=True)

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        # Basic command handlers
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_error_handler(error_handler)

        # Start polling
        logger.info("Starting polling...")
        updater.start_polling()
        logger.info("Bot started successfully!")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except TelegramError as te:
        logger.error(f"Telegram Error: {te}", exc_info=True)
    except Exception as e:
        logger.error(f"Critical error in main: {e}", exc_info=True)

if __name__ == '__main__':
    main()