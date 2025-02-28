import logging
import os
import signal
import sys
import time
from datetime import datetime

# Configure root logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)

if __name__ == "__main__":
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Starting Telegram bot in deployment mode...")

        # Set deployment flag
        os.environ['BOT_DEPLOYMENT'] = 'true'

        while True:  # Infinite loop for persistence
            try:
                # Initial startup check
                token = os.environ.get("TELEGRAM_TOKEN")
                if not token:
                    logger.critical("TELEGRAM_TOKEN not found in environment!")
                    raise ValueError("Missing TELEGRAM_TOKEN")

                logger.info("Starting bot process...")
                start_time = datetime.now()

                # Import and start the bot here to ensure fresh imports on restart
                from bot import main as bot_main
                bot_main()

                # If bot_main returns normally, log and continue
                uptime = datetime.now() - start_time
                logger.info(f"Bot process completed after {uptime}, restarting...")
                time.sleep(30)  # Wait before restart

            except Exception as e:
                uptime = datetime.now() - start_time
                logger.error(
                    f"Bot process crashed:\n"
                    f"Uptime: {uptime}\n"
                    f"Error: {str(e)}",
                    exc_info=True
                )
                logger.info("Restarting bot process in 30 seconds...")
                time.sleep(30)
                continue

    except Exception as e:
        logger.critical(f"Critical error in main process: {str(e)}", exc_info=True)
        sys.exit(1)