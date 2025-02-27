import logging
import os
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.error import NetworkError, TelegramError

# Configure detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    logger.debug(f"Start command received from user {update.effective_user.id}")
    update.message.reply_text('Hi! Bot is working! 🎵')

def main():
    """Start the bot with reliable configuration."""
    try:
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("TELEGRAM_TOKEN not found!")
            return

        logger.info("Starting bot initialization...")

        # Initialize with more robust settings
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 10,
                'connect_timeout': 10,
                'pool_timeout': 10
            }
        )

        # Get the dispatcher to register handlers
        dispatcher = updater.dispatcher

        # Add command handler
        dispatcher.add_handler(CommandHandler("start", start))

        # Add error handler
        def error_callback(update: Update, context: CallbackContext):
            try:
                raise context.error
            except NetworkError:
                logger.error("Network error occurred")
            except TelegramError:
                logger.error("Telegram API error occurred")
            except Exception as e:
                logger.error(f"An error occurred: {str(e)}")

        dispatcher.add_error_handler(error_callback)

        # Log connection attempt
        logger.info("Testing bot connection...")
        me = updater.bot.get_me()
        logger.info(f"Bot connection successful. Username: {me.username}")

        # Start the Bot with reliable settings
        logger.info("Starting polling...")
        updater.start_polling(
            timeout=30,
            read_latency=2,
            drop_pending_updates=True,
            bootstrap_retries=5
        )

        logger.info("Bot is running! Press Ctrl+C to stop.")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error occurred: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()