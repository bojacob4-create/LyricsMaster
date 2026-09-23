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

# Lazily-initialized translator (round 6 QA): the old code ran
# get_translator() once at import; if it failed (proxy hiccup, googletrans
# outage) translations were dead until the next restart. Now the first use
# (and any later failure) re-probes, at most once every 60s.
translator = None
_translator_last_probe = 0.0


def _get_translator():
    global translator, _translator_last_probe
    if translator is not None:
        return translator
    now = time.time()
    if now - _translator_last_probe < 60:
        return None
    _translator_last_probe = now
    translator = get_translator()
    return translator


@lru_cache(maxsize=100)
def translate_chunk(text: str, dest_lang: str = 'ar') -> Optional[str]:
    """Translate a single chunk of text with caching."""
    try:
        t = _get_translator()
        if not t:
            logger.error("Translator not initialized")
            return None

        if not text:
            return None

        translation = translator.translate(text, dest=dest_lang)
        return translation.text if translation else None

    except Exception as e:
        logger.error(f"Error translating chunk: {e}")
        return None

SUPPORTED_LANGUAGES = {
    'arabic': 'ar', 'ar': 'ar',
    'spanish': 'es', 'es': 'es',
    'french': 'fr', 'fr': 'fr',
    'german': 'de', 'de': 'de',
    'italian': 'it', 'it': 'it',
    'portuguese': 'pt', 'pt': 'pt',
    'turkish': 'tr', 'tr': 'tr',
    'russian': 'ru', 'ru': 'ru',
    'japanese': 'ja', 'ja': 'ja',
    'korean': 'ko', 'ko': 'ko',
    'chinese': 'zh-cn', 'zh': 'zh-cn',
    'hindi': 'hi', 'hi': 'hi',
    'dutch': 'nl', 'nl': 'nl',
    'polish': 'pl', 'pl': 'pl',
    'swedish': 'sv', 'sv': 'sv',
    'indonesian': 'id', 'id': 'id',
    'thai': 'th', 'th': 'th',
    'vietnamese': 'vi', 'vi': 'vi',
    'greek': 'el', 'el': 'el',
    'hebrew': 'he', 'he': 'he',
    'urdu': 'ur', 'ur': 'ur',
    'persian': 'fa', 'fa': 'fa',
    'malay': 'ms', 'ms': 'ms',
    'filipino': 'tl', 'tl': 'tl',
    'swahili': 'sw', 'sw': 'sw',
    'romanian': 'ro', 'ro': 'ro',
    'czech': 'cs', 'cs': 'cs',
    'hungarian': 'hu', 'hu': 'hu',
    'danish': 'da', 'da': 'da',
    'finnish': 'fi', 'fi': 'fi',
    'norwegian': 'no', 'no': 'no',
    'ukrainian': 'uk', 'uk': 'uk',
    'bengali': 'bn', 'bn': 'bn',
}

LANGUAGE_DISPLAY_NAMES = {
    'ar': 'Arabic', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'it': 'Italian', 'pt': 'Portuguese', 'tr': 'Turkish', 'ru': 'Russian',
    'ja': 'Japanese', 'ko': 'Korean', 'zh-cn': 'Chinese', 'hi': 'Hindi',
    'nl': 'Dutch', 'pl': 'Polish', 'sv': 'Swedish', 'id': 'Indonesian',
    'th': 'Thai', 'vi': 'Vietnamese', 'el': 'Greek', 'he': 'Hebrew',
    'ur': 'Urdu', 'fa': 'Persian', 'ms': 'Malay', 'tl': 'Filipino',
    'sw': 'Swahili', 'ro': 'Romanian', 'cs': 'Czech', 'hu': 'Hungarian',
    'da': 'Danish', 'fi': 'Finnish', 'no': 'Norwegian', 'uk': 'Ukrainian',
    'bn': 'Bengali',
}


def get_language_code(lang_name: str) -> Optional[str]:
    return SUPPORTED_LANGUAGES.get(lang_name.lower().strip())


def get_language_display(lang_code: str) -> str:
    return LANGUAGE_DISPLAY_NAMES.get(lang_code, lang_code.upper())


def get_supported_languages_text() -> str:
    main_langs = ['Arabic', 'Spanish', 'French', 'German', 'Italian',
                  'Portuguese', 'Turkish', 'Russian', 'Japanese', 'Korean',
                  'Chinese', 'Hindi', 'Dutch', 'Polish', 'Swedish']
    return ', '.join(main_langs) + ', and more'


def translate_to_arabic(text: str) -> Optional[str]:
    return translate_text(text, 'ar')


def translate_text(text: str, dest_lang: str = 'ar') -> Optional[str]:
    try:
        if not translator:
            logger.error("Translator not initialized")
            return None

        if not text:
            logger.warning("Empty text provided for translation")
            return None

        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        translated_chunks = []

        for chunk in chunks:
            translated_chunk = translate_chunk(chunk, dest_lang)
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