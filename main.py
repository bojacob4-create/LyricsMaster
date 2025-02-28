import logging
import os
import time
from datetime import datetime
from bot import main as bot_main

# Configure root logger with both file and console handlers
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,  # Changed to INFO for deployment
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_deployment.log')
    ]
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Starting Telegram bot in deployment mode...")
        # Set deployment flag
        os.environ['BOT_DEPLOYMENT'] = 'true'

        # Add deployment-specific exception handling
        max_restart_attempts = 5  # Increased from 3
        restart_count = 0

        while True:  # Infinite loop for persistence
            try:
                # Initial startup check
                token = os.environ.get("TELEGRAM_TOKEN")
                if not token:
                    logger.critical("TELEGRAM_TOKEN not found in environment!")
                    raise ValueError("Missing TELEGRAM_TOKEN")

                logger.info("Verified environment configuration...")
                start_time = datetime.now()

                # Start the bot with monitoring
                bot_main()

                # If bot_main returns normally, reset the restart counter
                restart_count = 0
                logger.info("Bot terminated normally, restarting...")
                time.sleep(10)  # Brief pause before restart
                continue

            except Exception as e:
                restart_count += 1
                uptime = datetime.now() - start_time
                logger.error(
                    f"Application crashed (attempt {restart_count}/{max_restart_attempts}):\n"
                    f"Uptime: {uptime}\n"
                    f"Error: {str(e)}",
                    exc_info=True
                )

                if restart_count < max_restart_attempts:
                    logger.info("Attempting automatic restart in 60 seconds...")  # Increased wait time
                    time.sleep(60)
                else:
                    logger.critical("Maximum restart attempts reached. Resetting counter...")
                    restart_count = 0  # Reset counter to allow for future restarts
                    time.sleep(120)  # Longer cooldown before starting fresh
                    continue  # Continue the outer loop

    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        # Don't raise the exception in deployment to prevent immediate exit
        if not os.environ.get('BOT_DEPLOYMENT'):
            raise