from googletrans import Translator
from typing import Optional
import logging
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

def get_translator():
    """Initialize translator with retries."""
    retries = 3
    for i in range(retries):
        try:
            translator = Translator()
            # Test the translator
            test_result = translator.translate('test', dest='ar')
            if test_result and test_result.text:
                logger.info("Translator initialized successfully")
                return translator
            logger.warning("Translator returned empty result during test")
        except Exception as e:
            logger.error(f"Attempt {i+1}/{retries} failed to initialize translator: {e}")
            if i < retries - 1:
                time.sleep(1)  # Wait before retrying
    return None

# Initialize translator
translator = get_translator()

@lru_cache(maxsize=100)
def translate_chunk(text: str, dest_lang: str = 'ar') -> Optional[str]:
    """Translate a single chunk of text with caching."""
    try:
        if not translator:
            logger.error("Translator not initialized")
            return None

        if not text:
            return None

        translation = translator.translate(text, dest=dest_lang)
        return translation.text if translation else None

    except Exception as e:
        logger.error(f"Error translating chunk: {e}")
        return None

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

        # Split text into smaller chunks to avoid length limitations
        # and to leverage caching effectively
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        translated_chunks = []

        for chunk in chunks:
            translated_chunk = translate_chunk(chunk)
            if translated_chunk:
                translated_chunks.append(translated_chunk)
            else:
                logger.warning("Received empty translation for chunk")

        if not translated_chunks:
            logger.error("No chunks were successfully translated")
            return None

        result = '\n'.join(translated_chunks)
        return result

    except Exception as e:
        logger.error(f"Error translating text: {e}")
        return None