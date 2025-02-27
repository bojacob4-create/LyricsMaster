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
    download_command,
    subscribe_daily_command,
    unsubscribe_daily_command,
    wiki_command
)
from datetime import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Start the bot."""
    try:
        # Get token from environment variable
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("No token provided!")
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")

        logger.info("Starting bot initialization...")

        # Initialize the bot
        updater = Updater(token=token, use_context=True)
        dp = updater.dispatcher

        # Register command handlers
        command_handlers = [
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("lyrics", lyrics_command),
            CommandHandler("stats", stats_command),
            CommandHandler("recommend", recommend_command),
            CommandHandler("quiz", quiz_command),
            CommandHandler("endquiz", end_quiz_command),
            CommandHandler("translate", translate_lyrics_command),
            CommandHandler("youtube", youtube_command),
            CommandHandler("analyze", analyze_command),
            CommandHandler("subscribe", subscribe_daily_command),
            CommandHandler("unsubscribe", unsubscribe_daily_command),
            CommandHandler("download", download_command),
            CommandHandler("wiki", wiki_command),
        ]

        for handler in command_handlers:
            dp.add_handler(handler)

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Schedule daily song job
        job_queue = updater.job_queue
        job_queue.run_daily(
            send_daily_song,
            time=time(hour=12, minute=0),
            days=(0, 1, 2, 3, 4, 5, 6)
        )

        # Set commands list with detailed descriptions (from original code)
        commands = [
            BotCommand("start", "Begin your musical journey 🎵"),
            BotCommand("help", "Get detailed help and tips 💡"),
            BotCommand("lyrics", "Find song lyrics with mood analysis 🎤"),
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
            BotCommand("wiki", "Search Wikipedia for music-related information 📚"),

        ]
        updater.bot.set_my_commands(commands)


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