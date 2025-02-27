import logging
import os
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
        bot_main()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        # Don't raise the exception in deployment to prevent immediate exit
        if not os.environ.get('BOT_DEPLOYMENT'):
            raise