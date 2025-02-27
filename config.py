import os
import logging

logger = logging.getLogger(__name__)

class Config:
    """Base configuration."""
    # Flask configuration
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'default-secret-key-for-development')

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # Telegram configuration
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

    # Production settings
    DEBUG = False
    TESTING = False

    # Logging configuration
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    @staticmethod
    def init_app(app):
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = logging.DEBUG

class ProductionConfig(Config):
    """Production configuration."""
    # Additional production-specific settings
    PREFERRED_URL_SCHEME = 'https'

    @staticmethod
    def init_app(app):
        Config.init_app(app)

        # Configure production logging
        if not app.debug and not app.testing:
            import logging
            from logging.handlers import RotatingFileHandler

            # Ensure logs directory exists
            if not os.path.exists('logs'):
                os.mkdir('logs')

            # Set up file handler
            file_handler = RotatingFileHandler(
                'logs/telegram_bot.log',
                maxBytes=10240000,
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s '
                '[in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)

            # Log application startup
            app.logger.info('Telegram Bot startup')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}