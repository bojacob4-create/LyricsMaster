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

Systemic calibration rules (applied in _apply_safety_calibration):
  These rules are NOT per-song hardcodes.  They are logical invariants:
  - You cannot fetch the right lyrics/song without knowing the artist
  - A single word with no artist can refer to hundreds of different songs
  - Empty entity extraction (no artist, no song) means there is nothing to act on
  These rules cap confidence AFTER the model responds, ensuring the
  LLM's over-confidence does not propagate to the routing layer.
"""

import os
import json
import logging
import hashlib
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Last.fm search constants ───────────────────────────────────────────────
_LASTFM_BASE   = "http://ws.audioscrobbler.com/2.0/"
_SEARCH_LIMIT  = 8    # fetch more so we have room to filter
_DOM_RATIO     = 4.0  # top result is dominant if listeners ≥ DOM_RATIO × #2

# ── Candidate quality filter ───────────────────────────────────────────────
# Words that indicate a track is not a clean original — covers, remixes, etc.
# Applied to the TRACK NAME (case-insensitive).  Never applied to artist name.
_FILTER_WORDS = frozenset({
    "remix", "cover", "karaoke", "instrumental", "version",
    "lyrics", "tribute", "acoustic", "piano", "mashup",
    "medley", "parody", "reprise", "edit", "remaster",
})


def search_song_candidates(song_name: str) -> List[Dict]:
    """
    Search Last.fm for real tracks matching song_name (no artist given).

    Returns a list of dicts (sorted descending by listener count):
        [{"artist": "...", "song": "...", "listeners": int}, ...]

    Maximum _SEARCH_LIMIT results, never raises.
    Returns [] on any failure.

    This function is the only source of truth for disambiguation —
    it NEVER invents artist names.
    """
    try:
        api_key = os.environ.get("LASTFM_API_KEY", "")
        if not api_key:
            logger.debug("[NLP][search] LASTFM_API_KEY not set")
            return []

        r = requests.get(
            _LASTFM_BASE,
            params={
                "method":  "track.search",
                "track":   song_name,
                "api_key": api_key,
                "format":  "json",
                "limit":   _SEARCH_LIMIT,
            },
            timeout=5,
        )
        r.raise_for_status()
        data    = r.json()
        matches = (
            data.get("results", {})
                .get("trackmatches", {})
                .get("track", [])
        )

        results = []
        for t in matches:
            artist_name = (t.get("artist") or "").strip()
            track_name  = (t.get("name")   or "").strip()
            listeners   = int(t.get("listeners", 0) or 0)
            if not artist_name or not track_name:
                continue
            # Quality filter: skip covers, remixes, karaoke, etc.
            # Check each word in track name against the filter list.
            track_lower = track_name.lower()
            if any(fw in track_lower for fw in _FILTER_WORDS):
                logger.debug(
                    f"[NLP][search] filtered dirty track: "
                    f"{artist_name!r} - {track_name!r}"
                )
                continue
            results.append({
                "artist":    artist_name,
                "song":      track_name,
                "listeners": listeners,
            })

        # Sort by listener count descending; Last.fm already returns them
        # ranked, but an explicit sort makes the contract explicit.
        results.sort(key=lambda x: x["listeners"], reverse=True)
        # Cap at 3 clean results
        results = results[:3]
        logger.debug(
            f"[NLP][search] song={song_name!r} → {len(results)} clean candidates"
        )
        return results

    except Exception as e:
        logger.warning(f"[NLP][search] search_song_candidates failed: {e}")
        return []


def is_dominant_match(candidates: List[Dict]) -> bool:
    """
    Return True if the top candidate is dominant — i.e. it is so far ahead
    of all others in listener count that showing multiple options would be
    misleading.

    Conditions for dominance:
      - Only one candidate found, OR
      - Top candidate has ≥ DOM_RATIO × the next candidate's listeners
    """
    if len(candidates) == 0:
        return False
    if len(candidates) == 1:
        return True
    top  = candidates[0]["listeners"]
    next_ = candidates[1]["listeners"]
    # Guard: if next_ is 0, avoid division by zero; treat as dominant
    if next_ == 0:
        return True
    return (top / next_) >= _DOM_RATIO


def disambiguation_message(
    song_name: str,
    intent:    str,
    candidates: List[Dict],
) -> str:
    """
    Build a user-facing disambiguation message.

    Three cases:
      A) Dominant single match → "Did you mean The Weeknd — Blinding Lights?"
      B) Multiple matches      → list top ≤ 3 real options with command hints
      C) No results            → generic "use Artist - Song" format prompt

    NEVER fabricates artist names.  Only uses data from candidates.
    """
    _INTENT_LABELS = {
        "lyrics":    "lyrics for",
        "song":      "info on",
        "recommend": "songs similar to",
        "analyze":   "an analysis of",
    }
    action = _INTENT_LABELS.get(intent, "info on")

    _INTENT_CMD = {
        "lyrics":    "/lyrics",
        "song":      "/song",
        "recommend": "/recommend",
        "analyze":   "/analyze",
    }
    cmd = _INTENT_CMD.get(intent, "/lyrics")

    if not candidates:
        # Case C — nothing found
        return (
            f"🔍 I couldn't find a song called *{song_name}*.\n\n"
            f"Please use the format:\n"
            f"`Artist - Song`\n\n"
            f"Example: `Tyla - Water`"
        )

    if is_dominant_match(candidates):
        # Case A — one clearly dominant real match.
        # For recommend: show a clean yes/no prompt — the pending_confirmation
        # state handles "yes" (→ execute) and "no" (→ fallback hint).
        # For other intents: keep the command hint so users can act without typing.
        top = candidates[0]
        if intent == "recommend":
            return f"🎵 Did you mean *{top['artist']}* — *{top['song']}*?"
        return (
            f"🎵 Did you mean *{top['artist']}* — *{top['song']}*?\n\n"
            f"Reply: `{cmd} {top['artist']} - {top['song']}`\n"
            f"or type `Artist - Song` to choose a different version."
        )

    # Case B — multiple plausible matches
    top3 = candidates[:3]
    lines = []
    for c in top3:
        lines.append(f"• `{cmd} {c['artist']} - {c['song']}`")

    options_str = "\n".join(lines)
    return (
        f"🎵 Several songs match *{song_name}*.\n"
        f"Which one did you mean?\n\n"
        f"{options_str}\n\n"
        f"Or type: `Artist - {song_name}` to be more specific."
    )

# ── Model ──────────────────────────────────────────────────────────────────
# gpt-5.4-mini confirmed available via OpenAI models API.
# Override with OPENAI_NLP_MODEL env var if needed.
_MODEL = os.environ.get("OPENAI_NLP_MODEL", "gpt-5.4-mini")

# ── In-process cache ───────────────────────────────────────────────────────
# MD5 of lowercased input → result dict.  Same message never hits the API
# twice within the same process lifetime.
_CACHE: Dict[str, dict] = {}

# ── System prompt ──────────────────────────────────────────────────────────
# Placed inside the input list (as a system role message) so that the
# Responses API json_object format requirement is satisfied — this prompt
# contains the word "JSON".
_SYSTEM_PROMPT = """\
You are a music bot intent parser. Your only job is to classify a user's
natural language message and extract music entities.

Return ONLY this JSON object — no explanation, no extra text:

{
  "intent": "lyrics | song | recommend | analyze | unknown",
  "artist": "string or null",
  "song": "string or null",
  "confidence": 0.0 to 1.0
}

=== INTENT DEFINITIONS ===
  lyrics    → user wants to READ the lyrics of a specific song
  song      → user wants info or a dashboard for ONE specific song
  recommend → user wants song recommendations or songs similar to something,
              OR wants to discover music from/like a specific artist.
              Use recommend when the user says "play something by X",
              "songs by X", "music by X", "give me songs by X",
              "play songs by X", or any phrasing that means
              "show me music FROM this artist" without naming one song.
  analyze   → user wants a deep lyric or theme analysis of a specific song
  unknown   → intent is not clear or not music-related

=== CONFIDENCE CALIBRATION — READ CAREFULLY ===

Confidence must reflect the quality of the FULL result (intent + entities),
NOT just how clearly you detected the intent.

Rules for when confidence must be LOW (below 0.5):
  - artist is null AND song name is a single common word (could match hundreds
    of songs — e.g. everyday words like "hello", "stay", "water", "love")
  - no artist AND no song could be extracted from the message
  - the message is so short or vague that multiple very different
    interpretations are equally plausible
  - the user only said the intent keyword (e.g. "lyrics", "songs") with
    nothing else to identify a specific track
  - you are guessing or inferring the artist from a popular association
    (e.g. hearing a song title and inferring the most famous artist who has
    that title) rather than the user explicitly naming them

Rules for when confidence should be MEDIUM (0.4–0.69):
  - intent is clear but only ONE of artist/song is identified
  - the artist or song could plausibly refer to multiple people/tracks
  - the phrasing is indirect or requires inference

Rules for when confidence may be HIGH (0.70+):
  - intent is unmistakably clear
  - AND artist is explicitly named by the user
  - AND song is explicitly named by the user
  - OR for recommend/analyze: at least one clearly identifiable, unambiguous
    entity (artist or song) is explicitly stated by the user

=== ENTITY EXTRACTION ===
  - Extract artist and song ONLY from what the user EXPLICITLY says
  - Do NOT infer or hallucinate the artist from a popular song name
  - If a song name is widely associated with one artist but the user did
    NOT name the artist, set artist to null
  - If the input is ambiguous (could be many different songs), set
    confidence below 0.5 even if the intent seems clear
  - Preserve the casing and spelling as the user wrote it

=== EXAMPLES OF CORRECT CALIBRATION ===
  "lyrics hello adele" → intent=lyrics artist=Adele song=Hello conf=0.95
  "hello" → intent=unknown artist=null song=null conf=0.10
  "blinding lights" → intent=song artist=null song=Blinding Lights conf=0.55
  "lyrics blinding lights" → intent=lyrics artist=null song=Blinding Lights conf=0.55
  "show lyrics" → intent=lyrics artist=null song=null conf=0.10
  "recommend me something like tame impala" → intent=recommend artist=Tame Impala song=null conf=0.82
  "analyze kill bill by sza"   → intent=analyze  artist=SZA        song=Kill Bill  conf=0.95
  "songs like counting stars onerepublic" → intent=recommend artist=OneRepublic song=Counting Stars conf=0.92
  "play something by adele"    → intent=recommend artist=Adele      song=null      conf=0.85
  "play songs by drake"        → intent=recommend artist=Drake      song=null      conf=0.85
  "give me music by the weeknd"→ intent=recommend artist=The Weeknd song=null      conf=0.85
  "pizza" → intent=unknown artist=null song=null conf=0.02

Return ONLY the JSON object.
"""

_FALLBACK = {"intent": "unknown", "artist": None, "song": None, "confidence": 0.0}

# ── Intents that require both artist AND song for high-confidence routing ──
_REQUIRES_ARTIST = {"lyrics", "song", "analyze"}


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


def _apply_safety_calibration(result: dict, raw_text: str) -> dict:
    """
    Apply post-model calibration rules that enforce logical invariants.

    These are NOT per-song hardcodes.  They are invariants that hold for
    ANY song, artist, and language:

    Rule 1 — No entities, no action:
        If neither artist nor song was extracted, the system cannot route
        meaningfully to any handler.  Cap confidence at 0.30.

    Rule 2 — Lyrics/song/analyze without an artist:
        These intents fetch data for ONE specific track.  Without the artist,
        the system does not know which version of the song to fetch, and the
        wrong result is certain.  Cap confidence at 0.55 (forces clarification).

    Rule 3 — Short input (≤ 2 words) without full entity pair:
        Very short inputs that lack both artist and song are almost always
        ambiguous.  Even if the model is confident, cap at 0.35.

    Rule 4 — Intent keyword with nothing else:
        If the intent is a music action (lyrics/recommend/etc.) but the
        remaining token count (after stripping the keyword) is 0, there is
        nothing to act on.  Cap at 0.20.
    """
    intent   = result.get("intent", "unknown")
    artist   = result.get("artist")
    song     = result.get("song")
    conf     = result.get("confidence", 0.0)
    words    = raw_text.strip().split()

    # Rule 1: no entities at all
    if not artist and not song:
        if conf > 0.30:
            logger.debug(f"[NLP][calibrate] Rule1 no-entities: {conf:.2f}→0.30 | {raw_text!r}")
            conf = 0.30

    # Rule 2: lyrics/song/analyze without artist (ambiguous which version)
    if intent in _REQUIRES_ARTIST and not artist:
        if conf > 0.55:
            logger.debug(f"[NLP][calibrate] Rule2 no-artist for {intent}: {conf:.2f}→0.55 | {raw_text!r}")
            conf = 0.55

    # Rule 3: very short input without both entities
    if len(words) <= 2 and not (artist and song):
        if conf > 0.35:
            logger.debug(f"[NLP][calibrate] Rule3 short-input no-pair: {conf:.2f}→0.35 | {raw_text!r}")
            conf = 0.35

    # Rule 4: only the intent keyword was typed, nothing else actionable
    _INTENT_KEYWORDS = {"lyrics", "recommend", "song", "analyze", "songs",
                        "lyric", "similar", "analysis"}
    remaining = [w for w in words if w.lower() not in _INTENT_KEYWORDS]
    if intent != "unknown" and len(remaining) == 0:
        if conf > 0.20:
            logger.debug(f"[NLP][calibrate] Rule4 keyword-only: {conf:.2f}→0.20 | {raw_text!r}")
            conf = 0.20

    result = dict(result)
    result["confidence"] = round(conf, 4)
    return result


def parse_intent(text: str) -> Dict:
    """
    Send user text to OpenAI Responses API and return structured intent + entities.

    Returns a dict:
        intent     — lyrics | song | recommend | analyze | unknown
        artist     — extracted artist name or None
        song       — extracted song name or None
        confidence — float 0.0–1.0, after safety calibration

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
        # OpenAI Responses API.
        # System prompt is a "system" role message inside `input` so that the
        # json_object format requirement (input must contain "json") is met.
        response = client.responses.create(
            model=_MODEL,
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            text={"format": {"type": "json_object"}},
            # Hard timeout: without this a hung API call blocks the user's
            # message handler indefinitely. 10s is generous for a mini model;
            # on timeout we fall back to the format hint via _FALLBACK.
            timeout=10,
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

    raw_song   = data.get("song") or None
    raw_artist = data.get("artist") or None

    # ── Post-model corrections ─────────────────────────────────────────────

    # 1) Null out placeholder song names the model sometimes fabricates.
    #    e.g. "play something by drake" → song="something" → null it.
    if raw_song and raw_song.lower().strip() in _PLACEHOLDER_SONGS:
        logger.debug(f"[NLP] Nulled placeholder song={raw_song!r}")
        raw_song = None

    # 2) Reclassify intent=song to intent=recommend when the user wants music
    #    FROM an artist (artist present, no specific song identified).
    #    "play something by X" / "give me songs by X" patterns.
    #    The model sometimes returns intent=song for these.
    if intent == "song" and raw_artist and not raw_song:
        logger.debug(
            f"[NLP] Reclassified song→recommend: artist={raw_artist!r} song=None"
        )
        intent = "recommend"

    result = {
        "intent":     intent,
        "artist":     raw_artist,
        "song":       raw_song,
        "confidence": float(data.get("confidence", 0.0)),
    }

    # Apply post-model safety calibration rules (systemic, not per-song)
    result = _apply_safety_calibration(result, text)

    logger.info(
        f"[NLP] model={_MODEL} intent={result['intent']!r} "
        f"artist={result['artist']!r} song={result['song']!r} "
        f"conf={result['confidence']:.2f} | input={text!r}"
    )

    _CACHE[key] = result
    return result


# ── Hallucinated / placeholder values the model may fabricate ─────────────
# These are systemic checks — not per-song hardcodes.
# If the model cannot identify a real value it sometimes fills these in.
_PLACEHOLDER_SONGS = frozenset({
    "something", "some song", "a song", "unknown", "that song",
    "this song", "it", "the song", "one", "anything",
})


def entity_gate(result: Dict, raw_text: str) -> str:
    """
    Mandatory second-layer safety check, independent of confidence score.

    Confidence answers: "How sure is the model?"
    This gate answers:  "Do we have enough correct data to act safely?"

    These are two separate questions.  A result can have high confidence AND
    still lack the entities required for safe execution — this gate catches that.

    Returns one of three routing decisions:
        'execute'  — entities are complete and valid for this intent
        'clarify'  — intent is recognisable but entities are missing/ambiguous
        'low_conf' — not enough to work with; ask for the Artist - Song format

    Rules (numbered to match specification):

    Rule 1 — lyrics / song / analyze require BOTH artist AND song.
        These intents fetch data for ONE specific track.  Without the artist,
        the system cannot know which version of the song to use; without the
        song, there is nothing to fetch.

    Rule 2 — Reject hallucinated / placeholder song values.
        The model sometimes fills "something", "some song", "unknown", etc.
        when it cannot identify the real song.  These must never be executed.

    Rule 3 — recommend requires at least one real entity (artist OR song).
        Recommendations need an anchor.  A vague request with no anchor
        cannot produce meaningful results.

    Rule 4 — Short inputs (≤ 2 words) without both artist + song.
        Very short inputs are almost always ambiguous.  Even at high model
        confidence they must not auto-execute without a complete entity pair.
    """
    intent = result.get("intent", "unknown")
    artist = result.get("artist")
    song   = result.get("song")
    words  = raw_text.strip().split()

    # Normalise for placeholder checks (case-insensitive)
    song_lower = (song or "").lower().strip()

    # Rule 2 — reject hallucinated placeholder song values (applied globally)
    if song and song_lower in _PLACEHOLDER_SONGS:
        logger.debug(f"[NLP][gate] Rule2 placeholder song={song!r} | {raw_text!r}")
        return "clarify"

    # Rule 1 — lyrics / song / analyze need both artist AND song.
    # Distinguish two sub-cases:
    #   a) Song is known but artist is missing  → clarify (ask for artist)
    #   b) Song is also missing (nothing to act on) → low_conf (ask for format)
    if intent in ("lyrics", "song", "analyze"):
        if not song:
            # No song at all — we have nothing specific to ask about
            logger.debug(
                f"[NLP][gate] Rule1a no song for {intent} | {raw_text!r}"
            )
            return "low_conf"
        if not artist:
            # Have a song but need the artist to fetch the right version
            logger.debug(
                f"[NLP][gate] Rule1b no artist for {intent}: song={song!r} | {raw_text!r}"
            )
            return "clarify"

    # Rule 3 — recommend needs at least one real entity
    if intent == "recommend":
        if not artist and not song:
            logger.debug(f"[NLP][gate] Rule3 recommend with no entities | {raw_text!r}")
            return "low_conf"

    # Rule 4 — short inputs (≤ 2 words) need both entities to auto-execute.
    # If the intent is unknown AND there are no entities at all, the system
    # has nothing specific to ask about → low_conf.
    # If intent or at least one entity is present, we can ask a targeted
    # question → clarify.
    if len(words) <= 2 and not (artist and song):
        if intent == "unknown" and not artist and not song:
            logger.debug(
                f"[NLP][gate] Rule4 short+empty — no intent or entities | {raw_text!r}"
            )
            return "low_conf"
        logger.debug(
            f"[NLP][gate] Rule4 short input, partial entities | {raw_text!r}"
        )
        return "clarify"

    return "execute"


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
            f"Try: `Artist - {song}`\n\n"
            f"Example: `Adele - {song}` or `The Weeknd - {song}`"
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
