"""
NLP Router — lightweight OpenAI-powered intent detection.

This module is a strictly non-intrusive add-on.  It is called ONLY when the
existing regex-based intent_router returns no match for a user message.

It does NOT:
  - generate recommendations
  - fetch lyrics or song data
  - produce analysis
  - modify any existing service, handler, or scoring logic

Its sole responsibility is to detect what the user wants (intent) and extract
the artist/song entity from free-form text, returning structured output that
the caller uses to route to an existing handler.

Routing is always done by the caller (handlers.py) using existing functions.
"""

import os
import json
import logging
import hashlib
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Model configuration ────────────────────────────────────────────────────
# The user spec requests "gpt-5.4-mini"; that model does not exist in the
# OpenAI API as of this implementation.  We default to gpt-4o-mini, which
# is the established cost-efficient model for lightweight classification tasks.
# Override by setting OPENAI_NLP_MODEL in environment.
_MODEL = os.environ.get("OPENAI_NLP_MODEL", "gpt-4o-mini")

# ── In-process cache ───────────────────────────────────────────────────────
# Keyed by MD5 of lowercased input to avoid repeat API calls for identical
# messages within the same process lifetime.
_CACHE: Dict[str, dict] = {}

# ── System prompt ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a music bot intent parser. Read the user's message and return ONLY a
JSON object with this exact structure — no extra text:

{
  "intent": "lyrics | song | recommend | analyze | unknown",
  "artist": "string or null",
  "song": "string or null",
  "confidence": 0.0 to 1.0
}

Rules:
- intent values and their meanings:
    lyrics    → user wants to read song lyrics
    song      → user wants general info / dashboard for a song
    recommend → user wants similar song suggestions
    analyze   → user wants a deep lyric/theme analysis
    unknown   → intent is unclear
- confidence reflects how certain you are about the full result (0.0–1.0)
- Extract artist and song only when you are confident they are correct
- If you cannot identify artist or song reliably, set them to null
- Do NOT invent or guess artist/song names
- Return ONLY the JSON object — nothing else
"""


def _cache_key(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()


def _get_client():
    """Lazy-load OpenAI client.  Returns None if key is absent or package missing."""
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


_FALLBACK = {"intent": "unknown", "artist": None, "song": None, "confidence": 0.0}


def parse_intent(text: str) -> Dict:
    """
    Send user text to OpenAI and return structured intent + entities.

    Returns a dict with keys:
        intent     — one of: lyrics, song, recommend, analyze, unknown
        artist     — extracted artist name or None
        song       — extracted song name or None
        confidence — float 0.0–1.0

    Never raises.  Returns _FALLBACK on any failure so the caller degrades
    gracefully to existing behaviour.
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
        # Chat Completions — stable across SDK versions and reliable with
        # json_object response_format (Responses API json_object requires
        # the literal word "json" in the user message, which our arbitrary
        # user inputs won't always contain).
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            response_format={"type": "json_object"},
            max_tokens=120,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[NLP] API call failed: {e}")
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
        f"[NLP] intent={result['intent']!r} artist={result['artist']!r} "
        f"song={result['song']!r} conf={result['confidence']:.2f} | input={text!r}"
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
    (0.4 ≤ confidence < 0.7).  Tells the user what the bot thinks they meant
    and how to confirm it precisely.
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
