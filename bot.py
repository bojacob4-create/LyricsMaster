import os
import logging
import asyncio
import sys
from typing import Optional, Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    try:
        user = update.effective_user
        logger.info(f"Start command from user {user.id}")
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I am your music bot! 🎵"
        )
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}", exc_info=True)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command handler."""
    try:
        logger.info(f"Help command from user {update.effective_user.id}")
        await update.message.reply_text(
            "Send /start to begin using the bot! 🎵"
        )
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}", exc_info=True)
        await update.message.reply_text("Sorry, something went wrong. Please try again.")

async def error_handler(update: Optional[object], context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

def main() -> None:
    """Start the bot."""
    try:
        # Get the token
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("No TELEGRAM_TOKEN provided")
            return

        logger.info("Starting bot initialization...")

        # Create application
        application = Application.builder().token(token).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_error_handler(error_handler)

        # Set commands
        async def setup_commands():
            await application.bot.set_my_commands([
                ("start", "Start the bot"),
                ("help", "Show help message")
            ])
            logger.info("Bot commands set successfully")

        # Run the bot
        logger.info("Starting bot...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
            close_loop=False,
            post_init=setup_commands
        )

    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()