from app import app
from bot import main
import logging

# Configure root logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Starting application...")
        main()
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        raise