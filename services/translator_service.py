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
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

# Breaker state is persisted to disk (round 68d) so a bot restart doesn't
# wipe it and burn 3 doomed Google attempts re-learning an ongoing outage.
_BREAKER_PATH = os.environ.get(
    "GTX_BREAKER_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        ".translate_breaker.json"))
_breaker_restored_open = False


def _breaker_persist() -> None:
    try:
        tmp = _BREAKER_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_gtx_breaker, f)
        os.replace(tmp, _BREAKER_PATH)
    except OSError as e:
        logger.warning(f"[translate] breaker state save failed: {e}")


def _breaker_restore() -> None:
    global _breaker_restored_open
    try:
        with open(_BREAKER_PATH) as f:
            st = json.load(f)
        _gtx_breaker["consec_429"] = int(st.get("consec_429", 0))
        _gtx_breaker["until"] = float(st.get("until", 0.0))
    except (OSError, ValueError):
        return
    # Logged lazily on first use: this module imports before the worker
    # configures logging, so an info() here would be silently dropped.
    _breaker_restored_open = _gtx_cooling_down()


def _gtx_cooling_down() -> bool:
    global _breaker_restored_open
    cooling = time.time() < _gtx_breaker["until"]
    if cooling and _breaker_restored_open:
        _breaker_restored_open = False
        logger.info(
            "[translate] gtx breaker restored from disk — Google treated "
            f"as down until "
            f"{time.strftime('%H:%M', time.localtime(_gtx_breaker['until']))}")
    return cooling


def _gtx_note_429() -> None:
    _gtx_breaker["consec_429"] += 1
    if _gtx_breaker["consec_429"] >= _GTX_BREAKER_TRIP:
        _gtx_breaker["until"] = time.time() + _GTX_COOLDOWN_S
        logger.warning(
            f"[translate] gtx 429 breaker tripped — Google treated as down "
            f"for {_GTX_COOLDOWN_S // 60}min, using fallback")
    _breaker_persist()


def _gtx_note_success() -> None:
    if _gtx_breaker["consec_429"]:
        _gtx_breaker["consec_429"] = 0
        _breaker_persist()


_breaker_restore()


# ── OpenAI fallback (round 68) ─────────────────────────────────────────────
# Same tiny model + lazy client pattern as the NLP layer.  Only fires when
# Google fails, so cost is ~zero (a song is a few hundred tokens at a
# fraction of a cent).
_OPENAI_MODEL = os.environ.get("OPENAI_NLP_MODEL", "gpt-5.4-mini")
_openai_client = None
_openai_client_tried = False

# ── Monthly fallback budget (round 68b, user-approved) ───────────────────────
# Hard cap on estimated OpenAI fallback spend per calendar month.  Token
# prices below are deliberately CONSERVATIVE (above any plausible mini-model
# pricing), so the cap trips early in estimated terms — real spend is
# guaranteed to stay under the budget when it trips.  Override with env vars
# for exact accounting.
_FALLBACK_BUDGET_USD = float(os.environ.get("OPENAI_FALLBACK_BUDGET_USD", "2.00"))
_FALLBACK_PRICE_IN_PER_1M = float(os.environ.get("OPENAI_FALLBACK_PRICE_IN", "2.00"))
_FALLBACK_PRICE_OUT_PER_1M = float(os.environ.get("OPENAI_FALLBACK_PRICE_OUT", "8.00"))
_BUDGET_PATH = os.environ.get(
    "TRANSLATE_BUDGET_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        ".translate_fallback_budget.json"))
_budget_tripped_logged = False
# Guards the budget file against concurrent fallback threads.  RLock so
# _budget_note can compose load+save atomically.  (The check-then-act gap
# between _budget_allow and _budget_note can overshoot by a call or two in
# a race — bounded to fractions of a cent by the conservative pricing.)
_budget_lock = threading.RLock()


def _budget_month():
    return time.strftime("%Y-%m")


def _budget_load():
    with _budget_lock:
        try:
            with open(_BUDGET_PATH) as f:
                st = json.load(f)
            if st.get("month") != _budget_month():
                return {"month": _budget_month(), "estimated_usd": 0.0}
            return {"month": st["month"],
                    "estimated_usd": float(st.get("estimated_usd", 0.0))}
        except (OSError, ValueError):
            return {"month": _budget_month(), "estimated_usd": 0.0}


def _budget_save(usd):
    with _budget_lock:
        try:
            tmp = _BUDGET_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"month": _budget_month(), "estimated_usd": usd}, f)
            os.replace(tmp, _BUDGET_PATH)
        except OSError as e:
            logger.warning(f"[translate] budget state save failed: {e}")


def _budget_allow():
    """True if the monthly fallback budget still has room."""
    global _budget_tripped_logged
    used = _budget_load()["estimated_usd"]
    if used >= _FALLBACK_BUDGET_USD:
        if not _budget_tripped_logged:
            _budget_tripped_logged = True
            logger.warning(
                f"[translate] monthly fallback budget exhausted "
                f"(${used:.2f} >= ${_FALLBACK_BUDGET_USD:.2f}) — fallback "
                f"disabled until {_budget_month()} rolls over")
        return False
    return True


def _budget_note(prompt_chars, completion_chars):
    """Record estimated spend for one fallback call (~4 chars/token)."""
    usd = ((prompt_chars / 4) / 1e6 * _FALLBACK_PRICE_IN_PER_1M
           + (completion_chars / 4) / 1e6 * _FALLBACK_PRICE_OUT_PER_1M)
    with _budget_lock:
        st = _budget_load()
        _budget_save(st["estimated_usd"] + usd)


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
    if not _budget_allow():
        return None
    client = _get_openai_client()
    if not client:
        return None
    lang_name = get_language_display(dest_lang) or dest_lang
    system = (
        f"You are a lyrics translator. Translate the user's song "
        f"lyrics to {lang_name}. Preserve line breaks and verse "
        f"structure exactly. Output ONLY the translation — no "
        f"commentary, no quotation marks.")
    try:
        response = client.responses.create(
            model=_OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            timeout=30,
        )
        result = response.output_text.strip()
        if result:
            _budget_note(len(system) + len(text), len(result))
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


def split_lyrics_chunks(text: str, max_chars: int = 1000) -> list:
    """Split lyrics into chunks of at most max_chars, breaking ONLY at
    line boundaries — never mid-word.  The old hard character slice could
    cut a word in half at a chunk edge (e.g. "Back that shit u" / "p"),
    leaving orphan fragments that leak into the translated output.
    "\n".join() of the result reproduces the input exactly.  A single
    pathological line longer than max_chars is hard-split as a last
    resort (astronomically rare in real lyrics)."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks, current, current_len = [], [], 0
    for line in text.split("\n"):
        if len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            chunks.extend(line[i:i + max_chars]
                          for i in range(0, len(line), max_chars))
            continue
        add = len(line) + (1 if current else 0)  # +1 for the re-added \n
        if current and current_len + add > max_chars:
            chunks.append("\n".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += add
    if current:
        chunks.append("\n".join(current))
    return chunks


def _translate_chunks_parallel(chunks, dest_lang):
    """Translate chunks concurrently (breaker-open path only).

    _gtx_translate short-circuits while the breaker is open, so each worker
    here is effectively an OpenAI call — safe to parallelize, unlike the
    Google path where concurrency would invite 429s.  Same tokens and cost
    as sequential, no burst-limit pause needed.  Order is preserved and
    failed chunks are dropped, matching the sequential path's semantics.
    """
    def _one(chunk):
        try:
            return translate_chunk(chunk, dest_lang)
        except Exception as e:
            logger.warning(f"[translate] parallel chunk failed: {e}")
            return None

    if len(chunks) == 1:
        single = _one(chunks[0])
        return [single] if single else []
    with ThreadPoolExecutor(max_workers=min(len(chunks), 5),
                            thread_name_prefix="tr-openai") as ex:
        results = list(ex.map(_one, chunks))
    kept = [r for r in results if r]
    if len(kept) < len(results):
        logger.warning(
            f"[translate] parallel path dropped {len(results) - len(kept)} "
            f"failed chunk(s)")
    return kept


def translate_text(text: str, dest_lang: str = 'ar') -> Optional[str]:
    try:
        if not text:
            logger.warning("Empty text provided for translation")
            return None

        chunks = split_lyrics_chunks(text)
        if _gtx_cooling_down():
            # Google is known down: every chunk goes to OpenAI — run them
            # concurrently instead of one-at-a-time with a Google pause.
            translated_chunks = _translate_chunks_parallel(chunks, dest_lang)
        else:
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
