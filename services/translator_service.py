from googletrans import Translator
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)

def get_translator():
    """Initialize translator with retries."""
    retries = 3
    for i in range(retries):
        try:
            translator = Translator()
            # Test the translator
            translator.translate('test', dest='ar')
            logger.info("Translator initialized successfully")
            return translator
        except Exception as e:
            logger.error(f"Attempt {i+1}/{retries} failed to initialize translator: {e}")
            if i < retries - 1:
                time.sleep(1)  # Wait before retrying
    return None

# Initialize translator
translator = get_translator()

def translate_to_arabic(text: str) -> Optional[str]:
    """
    Translate text to Arabic.

    Args:
        text (str): Text to translate

    Returns:
        Optional[str]: Translated text if successful, None otherwise
    """
    try:
        if not translator:
            logger.error("Translator not initialized")
            return None

        if not text:
            logger.warning("Empty text provided for translation")
            return None

        logger.info("Starting translation...")

        # Split text into smaller chunks to avoid length limitations
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        translated_chunks = []

        for chunk in chunks:
            try:
                translation = translator.translate(chunk, dest='ar')
                if translation and translation.text:
                    translated_chunks.append(translation.text)
            except Exception as chunk_error:
                logger.error(f"Error translating chunk: {chunk_error}")
                continue

        if not translated_chunks:
            logger.error("No chunks were successfully translated")
            return None

        result = '\n'.join(translated_chunks)
        logger.info("Translation completed successfully")
        return result

    except Exception as e:
        logger.error(f"Error translating text: {e}")
        return None