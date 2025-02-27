import logging
import os
from bot import main as bot_main

# Configure root logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Starting Telegram bot...")
        bot_main()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise