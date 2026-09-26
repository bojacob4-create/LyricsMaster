"""Translation service — requests-based Google Translate (gtx endpoint).

Round 39: replaced googletrans with a direct requests call to
translate.googleapis.com. googletrans's Translator() crashed at __init__ on
this host because httpx couldn't parse the NO_PROXY env var ('[::1]' ->
InvalidURL), and even bypassed, direct TLS to Google is blocked here —
traffic must go through the egress proxy. requests handles the proxy fine
(every other backend in this bot proves it), and a live probe confirmed
the gtx endpoint answers through it.

Public interface is unchanged: translate_text, translate_chunk,
translate_to_arabic, get_language_code, get_language_display,
get_supported_languages_text, SUPPORTED_LANGUAGES, LANGUAGE_DISPLAY_NAMES.
"""
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Undocumented but stable Google Translate endpoint used by browser clients.
_GTX_URL = "https://translate.googleapis.com/translate_a/single"
_GTX_TIMEOUT = 15
# This egress IP is throttled by Google on bursts: retry 429/5xx with backoff.
_GTX_MAX_ATTEMPTS = 3
_GTX_BACKOFFS = (2, 4)  # seconds before attempt 2 and 3
# Pause between chunks of a multi-chunk translation to stay under the burst
# limit (a song is several rapid requests otherwise).
_CHUNK_PAUSE = 0.5

# ── 429 circuit breaker (round 68) ─────────────────────────────────────────
# Google rate-limits this egress IP in waves that outlast any sane retry
# backoff (the 2026-09-26 wave 429'd every attempt for 20+ minutes).  After
# _GTX_BREAKER_TRIP consecutive 429 responses, Google is treated as down
# for _GTX_COOLDOWN_S and translate_chunk goes straight to the OpenAI
# fallback — no doomed retries, no retry-storm extending the ban.
_GTX_BREAKER_TRIP = 3
_GTX_COOLDOWN_S = 15 * 60
_gtx_breaker = {"consec_429": 0, "until": 0.0}


def _gtx_cooling_down() -> bool:
    return time.time() < _gtx_breaker["until"]


def _gtx_note_429() -> None:
    _gtx_breaker["consec_429"] += 1
    if _gtx_breaker["consec_429"] >= _GTX_BREAKER_TRIP:
        _gtx_breaker["until"] = time.time() + _GTX_COOLDOWN_S
        logger.warning(
            f"[translate] gtx 429 breaker tripped — Google treated as down "
            f"for {_GTX_COOLDOWN_S // 60}min, using fallback")


def _gtx_note_success() -> None:
    _gtx_breaker["consec_429"] = 0


# ── OpenAI fallback (round 68) ─────────────────────────────────────────────
# Same tiny model + lazy client pattern as the NLP layer.  Only fires when
# Google fails, so cost is ~zero (a song is a few hundred tokens at a
# fraction of a cent).
_OPENAI_MODEL = os.environ.get("OPENAI_NLP_MODEL", "gpt-5.4-mini")
_openai_client = None
_openai_client_tried = False


def _get_openai_client():
    """Lazy-load OpenAI client. Returns None if key absent or package missing."""
    global _openai_client, _openai_client_tried
    if _openai_client_tried:
        return _openai_client
    _openai_client_tried = True
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.debug("[translate] OPENAI_API_KEY not set — fallback disabled")
            return None
        _openai_client = OpenAI(api_key=api_key)
    except ImportError:
        logger.warning("[translate] openai package missing — fallback disabled")
    return _openai_client


def _openai_translate(text: str, dest_lang: str) -> Optional[str]:
    """Translate one chunk via OpenAI. Returns None on any failure."""
    if not text or not text.strip():
        return None
    client = _get_openai_client()
    if not client:
        return None
    lang_name = get_language_display(dest_lang) or dest_lang
    try:
        response = client.responses.create(
            model=_OPENAI_MODEL,
            input=[
                {"role": "system",
                 "content": (
                     f"You are a lyrics translator. Translate the user's song "
                     f"lyrics to {lang_name}. Preserve line breaks and verse "
                     f"structure exactly. Output ONLY the translation — no "
                     f"commentary, no quotation marks.")},
                {"role": "user", "content": text},
            ],
            timeout=30,
        )
        result = response.output_text.strip()
        return result or None
    except Exception as e:
        logger.error(f"[translate] OpenAI fallback failed (dest={dest_lang}): {e}")
        return None


def _gtx_translate(text: str, dest_lang: str) -> Optional[str]:
    """Translate one chunk via the gtx endpoint. Returns None on any failure."""
    if not text or not text.strip():
        return None
    if _gtx_cooling_down():
        # Breaker is open: don't burn requests (and user time) on a
        # rate-limited endpoint — the caller falls through to OpenAI.
        return None
    last_err = None
    for attempt in range(_GTX_MAX_ATTEMPTS):
        try:
            resp = requests.get(
                _GTX_URL,
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": dest_lang,
                    "dt": "t",
                    "q": text,
                },
                timeout=_GTX_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            # data[0] is a list of [translated, original, ...] segments.
            segments = data[0] if isinstance(data, list) and data else []
            parts = [seg[0] for seg in segments
                     if isinstance(seg, list) and seg and seg[0]]
            result = "".join(parts).strip()
            if result:
                _gtx_note_success()
            return result or None
        except requests.HTTPError as e:
            last_err = e
            status = e.response.status_code if e.response is not None else None
            if status == 429:
                _gtx_note_429()
            if status in (429, 500, 502, 503) and attempt < _GTX_MAX_ATTEMPTS - 1:
                wait = _GTX_BACKOFFS[attempt]
                logger.warning(
                    f"gtx translate got {status}, retrying in {wait}s "
                    f"(attempt {attempt + 1})")
                time.sleep(wait)
                continue
            logger.error(f"gtx translate HTTP failed (dest={dest_lang}): {e}")
            return None
        except Exception as e:
            last_err = e
            logger.error(f"gtx translate failed (dest={dest_lang}): {e}")
            return None
    logger.error(f"gtx translate exhausted retries (dest={dest_lang}): {last_err}")
    return None


# Success-only cache: failed translations (None) are never cached, so a
# transient outage doesn't permanently poison the result for that text.
_chunk_cache = {}
_CHUNK_CACHE_MAX = 100


def translate_chunk(text: str, dest_lang: str = 'ar') -> Optional[str]:
    """Translate a single chunk of text, caching only successful results.

    Google gtx is tried first (free, fast); when it fails — rate-limited,
    down, or breaker-tripped — the OpenAI fallback takes over so the user
    still gets a translation instead of "try again later".
    """
    key = (text, dest_lang)
    if key in _chunk_cache:
        return _chunk_cache[key]
    result = _gtx_translate(text, dest_lang)
    if result is None:
        result = _openai_translate(text, dest_lang)
    if result is not None:
        if len(_chunk_cache) >= _CHUNK_CACHE_MAX:
            _chunk_cache.pop(next(iter(_chunk_cache)))
        _chunk_cache[key] = result
    return result


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
        if not text:
            logger.warning("Empty text provided for translation")
            return None

        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        translated_chunks = []

        for i, chunk in enumerate(chunks):
            if i:
                time.sleep(_CHUNK_PAUSE)  # stay under Google's burst limit
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
