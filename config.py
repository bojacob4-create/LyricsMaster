import os
import logging

logger = logging.getLogger(__name__)

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'default-secret-key-for-development')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

    def __init__(self):
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set.\n"
                "Please ensure DATABASE_URL is set in your environment."
            )
        
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            logger.info("Converted postgres:// to postgresql:// in DATABASE_URL")
        
        self.SQLALCHEMY_DATABASE_URI = database_url

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

    def __init__(self):
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set.\n"
                "This is required for deployment.\n"
                "Please add DATABASE_URL to your deployment secrets."
            )
        
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            logger.info("Converted postgres:// to postgresql:// in DATABASE_URL")
        
        self.SQLALCHEMY_DATABASE_URI = database_url

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
