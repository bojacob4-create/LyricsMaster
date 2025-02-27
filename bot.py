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

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.error(f'Update "{update}" caused error "{context.error}"')

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        logger.info("Initializing bot...")

        # Initialize with optimized network settings
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 10,
                'connect_timeout': 10,
                'con_pool_size': 8,
                'proxy_url': None,
                'urllib3_proxy_kwargs': None
            }
        )

        logger.info("Testing bot connection...")
        me = updater.bot.get_me()
        logger.info(f"Bot connection successful. Username: {me.username}")

        # Get the dispatcher
        dp = updater.dispatcher
        logger.info("Dispatcher initialized")

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
            logger.info("Bot commands set successfully")
        except Exception as e:
            logger.warning(f"Failed to set commands: {str(e)}")

        # Start the Bot with optimized settings
        logger.info("Starting bot polling...")
        updater.start_polling(
            drop_pending_updates=True,
            bootstrap_retries=5,
            read_latency=1.0,
            timeout=30,
            clean=True
        )

        logger.info("Bot started successfully!")

        # Run the bot until you press Ctrl-C
        updater.idle()

    except TelegramError as te:
        logger.error(f"Telegram Error: {str(te)}")
        raise
    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()