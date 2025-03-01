import os
import logging
import signal
import time
from telegram.ext import Updater

def main():
    """Entry point for the bot."""
    try:
        # Get token from environment
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logging.error("TELEGRAM_TOKEN environment variable not set")
            return

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('bot.log')
            ]
        )
        
        logging.info("Starting bot from main.py...")
        
        # Import the bot module and run directly
        from bot import main as run_bot
        run_bot()
        
    except Exception as e:
        logging.exception(f"An error occurred in main.py: {str(e)}")


if __name__ == "__main__":
    main()