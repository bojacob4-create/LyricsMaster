import logging
import os
import sys
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
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
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Start the bot with simplified error handling."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        # Create the Updater and pass it your bot's token
        updater = Updater(token, use_context=True)

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        # Register commands
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

        # Start the Bot
        updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=['message', 'callback_query']
        )

        logger.info("Bot started successfully!")

        # Run the bot until it's stopped
        updater.idle()

    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
        raise  # Re-raise to let Flask handle the error

if __name__ == '__main__':
    main()