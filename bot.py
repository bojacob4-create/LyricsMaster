import logging
import os
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
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN not found")

        logger.info("Starting bot initialization...")

        # Create the Updater and pass it your bot's token
        updater = Updater(token=token, use_context=True)
        logger.debug("Updater created successfully")

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        # Register commands with logging
        def add_handler(handler):
            try:
                dp.add_handler(handler)
                logger.debug(f"Successfully added handler: {handler}")
            except Exception as e:
                logger.error(f"Failed to add handler {handler}: {str(e)}")

        # Add command handlers
        add_handler(CommandHandler("start", start_command))
        add_handler(CommandHandler("help", help_command))
        add_handler(CommandHandler("lyrics", lyrics_command))
        add_handler(CommandHandler("stats", stats_command))
        add_handler(CommandHandler("recommend", recommend_command))
        add_handler(CommandHandler("quiz", quiz_command))
        add_handler(CommandHandler("endquiz", end_quiz_command))
        add_handler(CommandHandler("translate", translate_lyrics_command))
        add_handler(CommandHandler("youtube", youtube_command))
        add_handler(CommandHandler("analyze", analyze_command))
        add_handler(CommandHandler("subscribe", subscribe_daily_command))
        add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
        add_handler(CommandHandler("download", download_command))
        add_handler(CommandHandler("wiki", wiki_command))

        # Add message handler for quiz answers
        add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        logger.info("All handlers registered successfully")

        # Start the Bot
        logger.info("Starting bot polling...")
        updater.start_polling(drop_pending_updates=True)
        logger.info("Bot polling started successfully!")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except Exception as e:
        logger.error(f"Critical error in bot initialization: {str(e)}")
        raise

if __name__ == '__main__':
    main()