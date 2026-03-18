"""
NLP Router — lightweight OpenAI-powered intent detection.

This module is a strictly non-intrusive add-on.  It is called ONLY when the
existing regex-based intent_router returns no match for a user message.

Responsibilities (ONLY):
  - detect user intent (lyrics / song / recommend / analyze / unknown)
  - extract artist and song names from free-form text

It does NOT:
  - generate recommendations
  - analyze songs
  - fetch lyrics
  - rewrite any bot responses
  - modify any existing service, handler, or scoring logic

Routing is always done by the caller (handlers.py) using existing functions.

Confidence tiers (enforced by caller in handlers.py):
  >= 0.7  → route to existing handler directly
  0.4–0.7 → ask user to clarify
  < 0.4   → ask user to use "Artist - Song" format
"""

import os
import json
import logging
import hashlib
from typing import Dict

logger = logging.getLogger(__name__)

# ── Model ──────────────────────────────────────────────────────────────────
# gpt-5.4-mini confirmed available via OpenAI models API.
# Override with OPENAI_NLP_MODEL env var if needed.
_MODEL = os.environ.get("OPENAI_NLP_MODEL", "gpt-5.4-mini")

# ── In-process cache ───────────────────────────────────────────────────────
# MD5 of lowercased input → result dict.  Same message never hits the API
# twice within the same process lifetime.
_CACHE: Dict[str, dict] = {}

# ── System prompt ──────────────────────────────────────────────────────────
# Placed inside the input list (not as `instructions`) so that the Responses
# API json_object format requirement ("input must contain 'json'") is met —
# this prompt contains the word "JSON".
_SYSTEM_PROMPT = """\
You are a music bot intent parser. Your only job is to read a user's natural
language message and return a structured JSON object.

Return ONLY this JSON object — no explanation, no extra text:

{
  "intent": "lyrics | song | recommend | analyze | unknown",
  "artist": "string or null",
  "song": "string or null",
  "confidence": 0.0 to 1.0
}

Intent definitions:
  lyrics    → user wants to read the lyrics of a song
  song      → user wants info or a dashboard for a song
  recommend → user wants song recommendations or similar songs
  analyze   → user wants a deep lyric or theme analysis
  unknown   → intent is unclear

Rules:
  - confidence is how sure you are about the full result (intent + entities)
  - Extract artist and song ONLY when confident they are correct
  - Do NOT invent or guess artist/song names
  - If artist or song cannot be reliably identified, set to null
  - Handle any natural language phrasing — do not assume specific keywords
  - Return ONLY the JSON object, nothing else
"""

_FALLBACK = {"intent": "unknown", "artist": None, "song": None, "confidence": 0.0}


def _cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()


def _get_client():
    """Lazy-load OpenAI client. Returns None if key absent or package missing."""
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.debug("[NLP] OPENAI_API_KEY not set — NLP layer disabled")
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        logger.warning("[NLP] openai package not installed — NLP layer disabled")
        return None


def parse_intent(text: str) -> Dict:
    """
    Send user text to OpenAI Responses API and return structured intent + entities.

    Returns a dict:
        intent     — lyrics | song | recommend | analyze | unknown
        artist     — extracted artist name or None
        song       — extracted song name or None
        confidence — float 0.0–1.0

    Never raises.  Returns _FALLBACK dict on any failure so the caller
    degrades gracefully without breaking existing bot behaviour.
    """
    text = (text or "").strip()
    if not text:
        return dict(_FALLBACK)

    key = _cache_key(text)
    if key in _CACHE:
        logger.debug(f"[NLP] Cache hit for: {text!r}")
        return _CACHE[key]

    client = _get_client()
    if not client:
        return dict(_FALLBACK)

    try:
        # Use the OpenAI Responses API.
        # The system prompt is placed as a "system" role message inside the
        # `input` list — this satisfies the API's requirement that the input
        # contains the word "json" when using text.format json_object mode.
        response = client.responses.create(
            model=_MODEL,
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            text={"format": {"type": "json_object"}},
        )
        raw = response.output_text.strip()
    except Exception as e:
        logger.error(f"[NLP] Responses API call failed ({type(e).__name__}): {e}")
        return dict(_FALLBACK)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[NLP] JSON parse error: {e} | raw={raw!r}")
        return dict(_FALLBACK)

    intent = data.get("intent", "unknown")
    if intent not in ("lyrics", "song", "recommend", "analyze", "unknown"):
        intent = "unknown"

    result = {
        "intent":     intent,
        "artist":     data.get("artist") or None,
        "song":       data.get("song") or None,
        "confidence": float(data.get("confidence", 0.0)),
    }

    logger.info(
        f"[NLP] model={_MODEL} intent={result['intent']!r} "
        f"artist={result['artist']!r} song={result['song']!r} "
        f"conf={result['confidence']:.2f} | input={text!r}"
    )

    _CACHE[key] = result
    return result


def build_query(result: Dict) -> str:
    """
    Build an 'Artist - Song' query string from NLP result for handler routing.
    Falls back to artist-only or song-only when one is missing.
    """
    artist = result.get("artist")
    song   = result.get("song")
    if artist and song:
        return f"{artist} - {song}"
    if artist:
        return artist
    if song:
        return song
    return ""


def clarification_message(result: Dict) -> str:
    """
    Return a user-facing clarification prompt for medium-confidence results
    (0.4 <= confidence < 0.7).
    """
    artist = result.get("artist")
    song   = result.get("song")
    intent = result.get("intent", "unknown")

    _INTENT_LABELS = {
        "lyrics":    "show lyrics for",
        "song":      "look up",
        "recommend": "find similar songs to",
        "analyze":   "analyze",
    }
    action = _INTENT_LABELS.get(intent, "search for")

    if artist and song:
        return (
            f"🤔 Did you mean to {action}:\n"
            f"  *{artist}* — *{song}*?\n\n"
            f"Reply with the exact format:\n"
            f"`/{intent} {artist} - {song}`"
        )
    if song:
        return (
            f"🤔 I found a song called *{song}*.\n"
            f"Could you add the artist name?\n\n"
            f"Try: `Artist - {song}`"
        )
    if artist:
        return (
            f"🤔 Did you mean the artist *{artist}*?\n"
            f"Which song would you like?\n\n"
            f"Try: `{artist} - Song Title`"
        )
    return (
        "🤔 I'm not quite sure what you're looking for.\n"
        "Use the format: `Artist - Song`\n\n"
        "Example: `The Weeknd - Blinding Lights`"
    )


def low_confidence_message() -> str:
    """
    Return a user-facing message for low-confidence results (< 0.4).
    Asks the user to be more specific with the 'Artist - Song' format.
    """
    return (
        "🎵 I wasn't able to understand your request.\n\n"
        "Please use the format:\n"
        "`Artist - Song`\n\n"
        "Examples:\n"
        "• `The Weeknd - Blinding Lights`\n"
        "• `SZA - Kill Bill`\n"
        "• `OneRepublic - Counting Stars`\n\n"
        "Or use a command directly:\n"
        "`/lyrics Artist - Song`\n"
        "`/recommend Artist - Song`"
    )
