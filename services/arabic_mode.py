"""
services/arabic_mode.py

Arabic Songs Mode — Fully Isolated, On-Demand Pipeline.
Self-contained. Does NOT import from or mutate any main bot service.

Architecture (real-time, per-request — NO background workers):
  Phase 1 — Identity Resolution (YouTube)
    Layer 1: YouTube search with original Arabic text
    Layer 2: YouTube search with normalized Arabic text
    Layer 5: YouTube search with romanized (transliterated) text  ← last resort
  Phase 2 — Scored lyrics retrieval (collect-all, score, pick best)
    Layer 2a: YouTube Music — collect ALL valid from top-5 results (ytmusicapi)
    Layer 3:  Genius API search → page scrape
    Layer 3b: Anghami kalimat — API song search → direct page fetch (per-request)
    Layer 4:  lrclib direct + search
    Layer 5b: aghanilyrics — DDG site: search → direct scrape (Referer required)
    Layer D:  General DuckDuckGo HTML search → multi-site scrape  ← last resort

Quality gate (_validate_arabic_lyrics) applied to every candidate:
  • Arabic-script ratio ≥ 0.70
  • Live/crowd contamination: < 2 distinct markers OR 1 marker on 2+ lines
  • Wrong-song guard: 1 strong token (len ≥ 4) OR ≥ 40% title token overlap
  • Content diversity: unique-line ratio ≥ 0.30 for blocks > 8 lines

Each passing candidate is scored by _score_lyrics_candidate() and all results
are collected before the best-scoring one is returned.
"""

import os
import re
import json
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Tuple, List, Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ── Dedicated HTTP session (Arabic mode only — NOT shared with main bot) ──────

_ar_session = requests.Session()
_ar_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
})

_GENIUS_KEY       = os.environ.get("GENIUS_API_KEY", "")
_GENIUS_SEARCH    = "https://api.genius.com/search"
_LRCLIB_GET       = "https://lrclib.net/api/get"
_LRCLIB_SEARCH    = "https://lrclib.net/api/search"
_YT_SEARCH_URL    = "https://www.youtube.com/results?search_query={}"
_DDG_SEARCH_URL   = "https://html.duckduckgo.com/html/"

# ── Anghami — on-demand fetch only (no crawling, no indexing) ──────────────
_ANGHAMI_LYRICS_BASE  = "https://kalimat.anghami.com/lyrics/{}"
_ANGHAMI_API_SEARCH   = "https://api.anghami.com/rest/v4/search.view"

# Live-performance / crowd-participation phrases.
# ≥ 2 matches in a single lyrics block → reject as live-contaminated.
_LIVE_SPEECH_MARKERS: frozenset = frozenset([
    "يلا معي", "هيا معي", "غنوا معي", "كلنا معي",
    "يا سلام هالحين", "مو حافظين", "الله يسلم",
    "شكراً لكم", "شكرا لكم", "مشكورين",
    "واحد اثنين ثلاثة", "ايش رأيكم",
])

# Domains that are app/streaming/social — never actual lyrics pages
_DDG_SKIP_DOMAINS: frozenset = frozenset([
    "youtube.com", "youtu.be", "google.com", "facebook.com",
    "twitter.com", "instagram.com", "tiktok.com", "wikipedia.org",
    "soundcloud.com", "spotify.com", "apple.com", "amazon.com",
    "deezer.com",
])

# Source confidence bonuses added to every candidate score.
# Higher = more trusted / more structured source.
_SOURCE_BONUS: Dict[str, int] = {
    "anghami":      40,
    "aghanilyrics": 35,
    "genius":       30,
    "ytmusic":      25,
    "lrclib":       15,
    "web":           0,
}

# If any candidate reaches this score, return immediately (early stop).
_HIGH_CONFIDENCE_SCORE = 75.0

# CSS selectors tried in order when scraping aghanilyrics.com pages.
_AGHANILYRICS_SELECTORS: List[str] = [
    "div.w3-display-container.w3-center.w3-ar",
    "div.w3-ar",
    "div[class*='w3-ar']",
]


# ════════════════════════════════════════════════════════════════════════════
# 0. NORMALIZATION + PARSING
# ════════════════════════════════════════════════════════════════════════════

_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_TATWEEL_RE    = re.compile(r"\u0640")


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for search matching.
    Returns a cleaned COPY — original display text is never overwritten.
    """
    text = re.sub(r"[–—\u2012\u2013\u2014\u2015]+", "-", text)
    text = _DIACRITICS_RE.sub("", text)
    text = _TATWEEL_RE.sub("", text)
    for ch in "أإآٱ":
        text = text.replace(ch, "ا")
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")   # ta-marbuta: حمزه ↔ حمزة both become حمزه
    text = text.replace("ؤ", "و")
    text = text.replace("ئ", "ي")
    text = text.replace("ء", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _validate_arabic_lyrics(lyrics: str, artist: str, song: str) -> bool:
    """
    Quality gate applied to every candidate lyrics block before acceptance.

    Checks (in order):
      1. Minimum length — must have ≥ 80 printable characters.
      2. Arabic-script ratio — non-whitespace chars must be ≥ 70 % Arabic.
      3. Live/crowd contamination — strict: ≥ 2 distinct markers OR 1 marker
         that appears on 2+ separate lines → reject.
      4. Wrong-song guard — need 1 strong token (len ≥ 4) in lyrics OR
         ≥ 40 % title-token overlap.  Skipped for very short titles.
      5. Diversity check — if block has > 8 non-trivial lines, unique-line
         ratio must be ≥ 0.30 (prevents copy-paste garbage).

    Returns True if acceptable, False if the block should be rejected.
    """
    if not lyrics or len(lyrics.strip()) < 80:
        return False

    # ── 1. Arabic ratio ≥ 70 % ───────────────────────────────────────────────
    non_ws = [c for c in lyrics if not c.isspace()]
    ar_chars = [c for c in non_ws if "\u0600" <= c <= "\u06ff"]
    ar_ratio = len(ar_chars) / len(non_ws) if non_ws else 0.0
    if ar_ratio < 0.70:
        logger.debug("[arabic][validate] rejected: low Arabic ratio (%.2f)", ar_ratio)
        return False

    # ── 2. Live/crowd contamination (strict) ─────────────────────────────────
    live_hits = sum(1 for m in _LIVE_SPEECH_MARKERS if m in lyrics)
    if live_hits >= 2:
        logger.debug("[arabic][validate] rejected: live contamination (%d markers)", live_hits)
        return False
    if live_hits == 1:
        # Check if the single marker appears on 2+ lines → repeated live speech
        lyr_lines = lyrics.split("\n")
        for marker in _LIVE_SPEECH_MARKERS:
            if sum(1 for ln in lyr_lines if marker in ln) >= 2:
                logger.debug("[arabic][validate] rejected: live marker repeated across lines")
                return False

    # ── 3. Wrong-song guard ──────────────────────────────────────────────────
    song_norm  = normalize_arabic(song)
    key_tokens = [t for t in song_norm.split() if len(t) > 2]
    if key_tokens:
        lyr_norm = normalize_arabic(lyrics)
        matches  = [t for t in key_tokens if t in lyr_norm]
        strong_match = any(len(t) >= 4 for t in matches)
        match_ratio  = len(matches) / len(key_tokens)
        if not strong_match and match_ratio < 0.40:
            logger.debug(
                "[arabic][validate] rejected: wrong song "
                "(%d/%d tokens, no strong match)", len(matches), len(key_tokens)
            )
            return False

    # ── 4. Content diversity check ───────────────────────────────────────────
    content_lines = [
        ln.strip() for ln in lyrics.split("\n")
        if ln.strip() and len(ln.strip()) > 3
    ]
    if len(content_lines) > 8:
        unique_ratio = len(set(content_lines)) / len(content_lines)
        if unique_ratio < 0.30:
            logger.debug(
                "[arabic][validate] rejected: low diversity (%.2f)", unique_ratio
            )
            return False

    return True


def _score_lyrics_candidate(lyrics: str, artist: str, song: str, source: str) -> float:
    """
    Score a lyrics candidate on a 0–100+ scale (source bonus can exceed 100).
    Higher score = stronger candidate.

    Components:
      • Arabic ratio      0–20  pts
      • Title token match 0–30  pts
      • Line structure    0–15  pts
      • Content diversity 0–10  pts
      • Source bonus      0–40  pts  (see _SOURCE_BONUS)
    Penalties:
      • Live marker hits  −15 pts each
      • High duplication  −10 or −20 pts
    """
    score = 0.0

    # 1. Arabic ratio (0–20)
    non_ws = [c for c in lyrics if not c.isspace()]
    ar_chars = [c for c in non_ws if "\u0600" <= c <= "\u06ff"]
    ar_ratio = len(ar_chars) / len(non_ws) if non_ws else 0.0
    score += ar_ratio * 20.0

    # 2. Title token match (0–30)
    song_norm  = normalize_arabic(song)
    key_tokens = [t for t in song_norm.split() if len(t) > 2]
    if key_tokens:
        lyr_norm = normalize_arabic(lyrics)
        matches  = sum(1 for t in key_tokens if t in lyr_norm)
        score   += (matches / len(key_tokens)) * 30.0
    else:
        score += 15.0  # no tokens to evaluate → neutral

    # 3. Line structure quality (0–15)
    lines = [ln.strip() for ln in lyrics.split("\n") if ln.strip() and len(ln.strip()) > 2]
    if len(lines) >= 16:
        score += 15.0
    elif len(lines) >= 8:
        score += 10.0
    elif len(lines) >= 4:
        score += 5.0

    # 4. Content diversity (0–10)
    if lines:
        diversity = len(set(lines)) / len(lines)
        score += diversity * 10.0

    # 5. Source bonus
    score += _SOURCE_BONUS.get(source, 0)

    # 6. Penalties
    live_hits = sum(1 for m in _LIVE_SPEECH_MARKERS if m in lyrics)
    score -= live_hits * 15.0

    if lines:
        dup_ratio = 1.0 - len(set(lines)) / len(lines)
        if dup_ratio > 0.50:
            score -= 20.0
        elif dup_ratio > 0.30:
            score -= 10.0

    return max(0.0, score)


_FORMAT_ERROR = (
    "Please use the correct format:\n"
    "Artist - Song\n\n"
    "Example:\n"
    "ماجد المهندس - ضايع"
)

_ARABIC_ONLY_ERROR = (
    "🎵 Arabic Mode only accepts Arabic artist and song names.\n\n"
    "Please enter Arabic text. Example:\n"
    "ماجد المهندس - ضايع\n\n"
    "To exit Arabic mode, send /exit"
)


def parse_arabic_input(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Strict 'artist - song' parser.
    Returns (artist, song, None) or (None, None, error_msg).

    Rejects input where either artist or song contains no Arabic characters.
    """
    text = re.sub(r"\s*[–—\u2012\u2013\u2014\u2015\-]+\s*", " - ", text.strip())
    if " - " not in text:
        return None, None, _FORMAT_ERROR
    parts = text.split(" - ", 1)
    artist, song = parts[0].strip(), parts[1].strip()
    if not artist or not song:
        return None, None, _FORMAT_ERROR
    # Both artist AND song must contain at least one Arabic character
    if not _has_arabic(artist) or not _has_arabic(song):
        return None, None, _ARABIC_ONLY_ERROR
    return artist, song, None


# ════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ════════════════════════════════════════════════════════════════════════════

_REJECT_WORDS = frozenset([
    "remix", "live", "cover", "karaoke", "slowed", "sped up",
    "reverb", "instrumental", "acoustic", "tribute", "mashup",
])

_REJECT_YT_WORDS = frozenset([
    "reaction", "review", "tutorial", "cover by", "karaoke",
    "instrumental", "remix by", "mashup", "parody", "behind the scenes",
    "interview", "podcast", "explained", "how to", "compilation",
    "top 10", "ranking", "tier list", "slowed", "reverb",
])

# Live/concert/TV terms — STRONG penalty so official always wins when both exist.
# Not a hard reject: if only concert versions exist, the penalized one can still win.
_LIVE_PENALTY_WORDS = frozenset([
    # English show / live / TV terms
    "live", "concert", "festival", "performance", "session",
    "show", "episode", "program", "broadcast", "audition", "stage",
    "arab idol", "the voice", "mbc",
    # Arabic concert / TV / festival terms
    "حفلة", "حفل", "حفلات", "مباشر", "سهرة", "جلسة",
    "مهرجان", "برنامج", "حلقة", "عرض",
])
_LIVE_PENALTY = 40   # strong enough to always lose to an official upload

# Official upload signals — applied to both the raw title and the channel name.
_OFFICIAL_BONUS_WORDS = frozenset([
    # English official title markers
    "official music video", "official audio", "official video",
    "official lyric", "official song", "music video",
    # Arabic official title markers
    "حصرياً", "حصرى", "حصري", "فيديو كليب", "كليب رسمي",
    "رسمي", "النسخة الأصلية",
])
# Major Arabic label / aggregator channels that host official releases.
# Checked against channel name (lowercase).
_OFFICIAL_CHANNELS = frozenset([
    "rotana", "روتانا", "vevo", " - topic",
    "mazzika", "mazika", "anghami",
])
_TITLE_BONUS   = 15   # title keyword (حصري, official video, etc.) — moderate signal
_CHANNEL_BONUS = 25   # Rotana/VEVO/Topic channel — authoritative official signal
_OFFICIAL_BONUS = _CHANNEL_BONUS  # alias kept for any legacy references


def _is_non_original(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in _REJECT_WORDS)


def _has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


# ════════════════════════════════════════════════════════════════════════════
# LAYER 5 HELPERS — Romanized transliteration (hidden fallback)
# ════════════════════════════════════════════════════════════════════════════

_AR_LATIN = str.maketrans({
    "ا": "a",  "ب": "b",  "ت": "t",  "ث": "th", "ج": "j",  "ح": "h",
    "خ": "kh", "د": "d",  "ذ": "dh", "ر": "r",  "ز": "z",  "س": "s",
    "ش": "sh", "ص": "s",  "ض": "d",  "ط": "t",  "ظ": "z",  "ع": "",
    "غ": "gh", "ف": "f",  "ق": "q",  "ك": "k",  "ل": "l",  "م": "m",
    "ن": "n",  "ه": "h",  "و": "w",  "ي": "y",  "ة": "a",  "ى": "a",
    "أ": "a",  "إ": "e",  "آ": "a",  "ء": "",   "ؤ": "w",  "ئ": "y",
})


def _romanize(text: str) -> str:
    text = normalize_arabic(text)
    result = text.translate(_AR_LATIN)
    return re.sub(r"\s+", " ", result).strip()


# ════════════════════════════════════════════════════════════════════════════
# PHASE 1 — LAYER 1 + 2: YouTube Identity Resolver
# ════════════════════════════════════════════════════════════════════════════

_YT_SUFFIX_RE = re.compile(
    r"\s*[\|\-]\s*("
    r"official\s*(music\s*)?video|official\s*audio|official\s*(lyric\s*)?clip|"
    r"official\s*lyric|hq\s*audio|full\s*song|"
    r"كليب\s*رسمي|فيديو\s*كليب|كليب|ليريكس|audio\s*official|lyrics"
    r").*",
    re.IGNORECASE,
)


def _yt_extract_candidates(html: str) -> List[Dict]:
    """Parse YouTube search HTML into candidate list with title + channel."""
    candidates = []
    match = re.search(r"var ytInitialData = ({.*?});\s*</script>", html, re.DOTALL)
    if not match:
        match = re.search(r"var ytInitialData = ({.*?});", html)
    if match:
        try:
            data = json.loads(match.group(1))
            contents = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for section in contents:
                items = section.get("itemSectionRenderer", {}).get("contents", [])
                for item in items:
                    vr = item.get("videoRenderer", {})
                    if not vr:
                        continue
                    vid     = vr.get("videoId", "")
                    title   = (vr.get("title", {}).get("runs", [{}])[0].get("text", ""))
                    channel = (vr.get("ownerText", {}).get("runs", [{}])[0].get("text", ""))
                    if vid and title:
                        candidates.append({"id": vid, "title": title, "channel": channel})
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"[arabic][yt] JSON parse error: {e}")

    if not candidates:
        ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        seen: set = set()
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                candidates.append({"id": vid, "title": "", "channel": ""})
            if len(candidates) >= 10:
                break

    return candidates[:10]


def _yt_parse_title(
    title: str, channel: str
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract (arabic_artist, arabic_song, english_artist, english_song).
    Handles:
      • "Artist - Song"
      • "Artist ... Song"                 (Rotana/label style)
      • "Arabic Artist - Song | English Artist - Song"  (bilingual)
      • "English - Song | Qualifier | Arabic - Song"    (reversed bilingual)
      • "Artist | Song"

    IMPORTANT: bilingual segment split is done BEFORE _YT_SUFFIX_RE is applied
    so that qualifier segments like "| Lyrics Video 2025 |" in the middle of a
    bilingual title do not strip the Arabic portion.
    """
    eng_artist: Optional[str] = None
    eng_song:   Optional[str] = None

    # ── Step 1: Bilingual segment split FIRST ────────────────────────────────
    # Split on " | " before any suffix stripping so Arabic portions are not lost.
    if " | " in title:
        segments = [s.strip() for s in title.split(" | ")]
        arabic_segs  = [s for s in segments if _has_arabic(s)]
        english_segs = [s for s in segments if not _has_arabic(s) and s]

        # Extract English alias from the first all-ASCII segment
        if english_segs:
            eng_seg = _YT_SUFFIX_RE.sub("", english_segs[0]).strip()
            eng_seg = re.sub(r"\s*\([^)]*\)\s*$", "", eng_seg).strip()
            if " - " in eng_seg:
                ep = eng_seg.split(" - ", 1)
                eng_artist, eng_song = ep[0].strip(), ep[1].strip()

        # Prefer the first Arabic segment; fall back to first segment overall
        raw = arabic_segs[0] if arabic_segs else segments[0]
        clean = _YT_SUFFIX_RE.sub("", raw).strip()
    else:
        # No bilingual separator — apply suffix stripping to the whole title
        clean = _YT_SUFFIX_RE.sub("", title).strip()

    # ── Step 2: Separator logic on the isolated clean segment ─────────────────

    # Primary: " - "
    if " - " in clean:
        parts = clean.split(" - ", 1)
        artist, song = parts[0].strip(), parts[1].strip()
        if artist and song:
            return artist, song, eng_artist, eng_song

    # Secondary: " ... " (Rotana / label style, e.g. "حسين الجسمي ... سته الصبح")
    if " ... " in clean:
        parts = clean.split(" ... ", 1)
        artist, song = parts[0].strip(), parts[1].strip()
        if artist and song:
            return artist, song, eng_artist, eng_song

    # Tertiary: " | " (shouldn't normally survive step 1, but kept for safety)
    if " | " in clean:
        parts = clean.split(" | ", 1)
        artist, song = parts[0].strip(), parts[1].strip()
        if artist and song:
            return artist, song, eng_artist, eng_song

    # Fallback: treat channel as artist, cleaned title as song
    if channel and clean:
        return channel.strip(), clean, eng_artist, eng_song

    return None, None, None, None


def _yt_compute_score(
    query_artist: str, query_song: str,
    cand_artist:  str, cand_song:   str,
    full_title:   str = "",
    channel:      str = "",
) -> float:
    """
    Combined score that handles both Arabic-to-Arabic and Arabic-to-English
    (transliterated) matches.

    Artist ≥ 60% threshold + Song ≥ 60% threshold → must both pass.
    Combined score: artist 50% + song 40% + clean title 10%.

    Adjustments applied to full_title and channel:
    - Live/concert/TV penalty: -40  (broadcast/concert always loses to official)
    - Official video bonus:    +20  (title keywords OR recognised label channel)
    Priority guarantee: if both an official and a concert version exist,
    official wins even if concert scores base 100.
    """
    from difflib import SequenceMatcher as _SM

    def _tok_overlap(q: str, c: str) -> float:
        qt = set(normalize_arabic(q).split()) | set(q.lower().split())
        qt = {t for t in qt if len(t) > 1}
        ct = set(normalize_arabic(c).split()) | set(c.lower().split())
        ct = {t for t in ct if len(t) > 1}
        if not qt:
            return 0.0
        return len(qt & ct) / len(qt)

    ar_artist = _tok_overlap(query_artist, cand_artist) * 50
    ar_song   = _tok_overlap(query_song,   cand_song)   * 40

    # Romanized comparison — compact char-level fuzzy matching handles vowel gaps
    # between Arabic romanization (e.g. "rashd almajd") and real transliterations
    # (e.g. "Rashed Al Majed").  SequenceMatcher on whitespace-stripped strings.
    rom_qa = _romanize(query_artist)
    rom_qs = _romanize(query_song)

    def _rom_overlap(rq: str, rc_raw: str) -> float:
        if not rq:
            return 0.0
        rc = rc_raw.lower()
        # Compact: keep only lowercase alpha chars for character-level comparison
        rq_c = re.sub(r"[^a-z]", "", rq.replace(" ", ""))
        rc_c = re.sub(r"[^a-z]", "", rc.replace(" ", ""))
        if not rq_c or not rc_c:
            return 0.0
        ratio = _SM(None, rq_c, rc_c).ratio()
        # Require ≥ 0.60 similarity before counting as a match
        return ratio if ratio >= 0.60 else 0.0

    rom_artist = _rom_overlap(rom_qa, cand_artist) * 50
    rom_song   = _rom_overlap(rom_qs, cand_song)   * 40

    artist_score = max(ar_artist, rom_artist)
    song_score   = max(ar_song,   rom_song)

    # ── Reversed-order check ("Song - Artist" format used by some uploaders) ──
    # If both thresholds fail, try swapping cand_artist ↔ cand_song.
    if (artist_score < 30 or song_score < 24) and cand_artist and cand_song:
        sw_ar_artist = _tok_overlap(query_artist, cand_song)   * 50
        sw_ar_song   = _tok_overlap(query_song,   cand_artist) * 40
        sw_rom_artist = _rom_overlap(rom_qa, cand_song)   * 50
        sw_rom_song   = _rom_overlap(rom_qs, cand_artist) * 40
        sw_artist = max(sw_ar_artist, sw_rom_artist)
        sw_song   = max(sw_ar_song,   sw_rom_song)
        if sw_artist >= 30 and sw_song >= 24:
            artist_score = sw_artist
            song_score   = sw_song

    # Strict artist + song threshold enforcement (≥ 60% each)
    if artist_score < 30 or song_score < 24:   # 30 = 60% of 50; 24 = 60% of 40
        return 0.0

    # Non-original penalty (remix, cover, karaoke, etc.)
    clean_bonus = 0 if _is_non_original(cand_song) else 10

    # Live / concert / TV penalty — checked against the FULL raw YouTube title
    # so secondary segments like "| حفل مفاجآت صيف دبي 2023" are also caught.
    tl = full_title.lower()
    live_pen = -_LIVE_PENALTY if any(w in tl for w in _LIVE_PENALTY_WORDS) else 0

    # Official upload bonus — two-tier signal strength:
    # • Known label channels (Rotana, VEVO, Topic) → stronger channel bonus
    # • Title keywords (حصري, official video) → moderate title bonus
    # Both bonuses can stack if a Rotana upload also has "official video" in title,
    # but normally only the highest applicable tier is used.
    ch_lower = channel.lower()
    channel_is_official = any(w in ch_lower for w in _OFFICIAL_CHANNELS)
    title_is_official   = any(w in tl for w in _OFFICIAL_BONUS_WORDS)
    if channel_is_official:
        official_bon = _CHANNEL_BONUS   # 25 — authoritative label upload
    elif title_is_official:
        official_bon = _TITLE_BONUS     # 15 — title keyword (less authoritative)
    else:
        official_bon = 0

    return artist_score + song_score + clean_bonus + live_pen + official_bon


def _yt_search(search_query: str) -> List[Dict]:
    """Fetch YouTube search results and return parsed candidate list."""
    try:
        url = _YT_SEARCH_URL.format(quote(search_query))
        r = _ar_session.get(url, timeout=7)
        if r.status_code == 200:
            return _yt_extract_candidates(r.text)
    except Exception as e:
        logger.debug(f"[arabic][yt] search failed (q={search_query!r}): {e}")
    return []


def _yt_resolve(
    query_artist: str,
    query_song:   str,
    search_query: str,
) -> Optional[Tuple[str, str, Optional[str], Optional[str], str]]:
    """
    Search YouTube with `search_query`, parse titles, score candidates.
    Returns (arabic_artist, arabic_song, eng_artist, eng_song, video_id) or None.
    video_id is the YouTube video ID of the best-matching result — use it to build
    a direct watch URL (https://youtube.com/watch?v=<video_id>) in Arabic mode.
    The English alias (eng_artist, eng_song) is captured from bilingual titles
    and passed to Phase 2 so Genius can be searched with it.
    """
    candidates = _yt_search(search_query)
    if not candidates:
        return None

    best_score  = 0.0
    best_result: Optional[Tuple[str, str, Optional[str], Optional[str], str]] = None

    for cand in candidates:
        vid     = cand.get("id", "")
        title   = cand.get("title", "")
        channel = cand.get("channel", "")

        if not title or not vid:
            continue

        # Hard reject non-original types
        if any(w in title.lower() for w in _REJECT_YT_WORDS):
            continue

        parsed_artist, parsed_song, eng_artist, eng_song = _yt_parse_title(title, channel)
        if not parsed_artist or not parsed_song:
            continue

        score = _yt_compute_score(query_artist, query_song, parsed_artist, parsed_song, title, channel)

        logger.debug(
            f"[arabic][yt] q={search_query!r}  vid={vid}  title={title!r}  "
            f"pa={parsed_artist!r}  ps={parsed_song!r}  "
            f"eng=({eng_artist!r}, {eng_song!r})  score={score:.1f}"
        )

        if score > best_score:
            best_score = score
            best_result = (parsed_artist, parsed_song, eng_artist, eng_song, vid)

    if best_result and best_score >= 40:
        logger.info(
            f"[arabic][yt] resolved: {best_result[0]!r} - {best_result[1]!r} "
            f"eng=({best_result[2]!r}, {best_result[3]!r}) vid={best_result[4]} score={best_score:.1f}"
        )
        return best_result

    return None


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LAYER 2a: YouTube Music lyrics (PRIMARY source — Arabic mode only)
# ════════════════════════════════════════════════════════════════════════════

_yt_music_client: Optional[object] = None


def _get_ytmusic():
    """Return a cached unauthenticated YTMusic client."""
    global _yt_music_client
    if _yt_music_client is None:
        try:
            from ytmusicapi import YTMusic
            _yt_music_client = YTMusic()
            logger.debug("[arabic][ytmusic] client initialized")
        except Exception as e:
            logger.warning(f"[arabic][ytmusic] init failed: {e}")
    return _yt_music_client


def _ytmusic_score(query_artist: str, query_song: str, cand_title: str, cand_artist: str) -> float:
    """
    Score a YouTube Music search result against the query.
    Returns 0-100. Accepts both Arabic and romanized candidate names.
    """
    def _overlap(q: str, c: str) -> float:
        qt = set(normalize_arabic(q).lower().split()) | set(q.lower().split())
        qt = {t for t in qt if len(t) > 1}
        ct = set(normalize_arabic(c).lower().split()) | set(c.lower().split())
        ct = {t for t in ct if len(t) > 1}
        if not qt:
            return 0.0
        return len(qt & ct) / len(qt)

    art_score  = _overlap(query_artist, cand_artist) * 50
    song_score = _overlap(query_song, cand_title) * 50
    return art_score + song_score


def _ytmusic_candidates(artist: str, song: str) -> List[Tuple[str, str]]:
    """
    Collect ALL valid YTMusic lyrics candidates from the top-5 results across
    all query forms (original Arabic, normalised Arabic, romanised).

    Each passing candidate is validated with _validate_arabic_lyrics() before
    being added.  Returns a list of (lyrics_text, "ytmusic") pairs — the caller
    is responsible for scoring.  Stops collecting after finding 2 valid results
    to avoid excessive API calls.

    Isolated to Arabic mode — does NOT touch the main bot's session or logic.
    """
    yt = _get_ytmusic()
    if not yt:
        return []

    orig_is_arabic = _has_arabic(artist) or _has_arabic(song)

    # Build query list: original → normalised → romanised (last resort)
    queries: List[Tuple[str, bool]] = [(f"{artist} {song}", True)]  # (query, is_arabic)
    norm_q = f"{normalize_arabic(artist)} {normalize_arabic(song)}"
    if norm_q.strip() != queries[0][0].strip():
        queries.append((norm_q, True))
    rom_q = f"{_romanize(artist)} {_romanize(song)}"
    if rom_q.strip() and rom_q.strip() not in [q for q, _ in queries]:
        queries.append((rom_q, False))

    found: List[Tuple[str, str]] = []
    seen_vids: set = set()
    arabic_found_count = 0  # tracks valid Arabic candidates so far

    for query, query_is_arabic in queries:
        # Skip romanised queries if we already found at least one Arabic candidate
        if not query_is_arabic and arabic_found_count > 0:
            break
        try:
            results = yt.search(query, filter="songs", limit=5)
        except Exception as e:
            logger.debug(f"[arabic][ytmusic] search failed for q={query!r}: {e}")
            continue
        if not results:
            continue

        for r in results[:5]:   # ytmusicapi may return more than requested — cap at 5
            vid   = r.get("videoId", "")
            title = r.get("title", "")
            arts  = r.get("artists") or []
            art   = arts[0].get("name", "") if arts else ""
            if not vid or not title or vid in seen_vids:
                continue
            if _is_non_original(title):
                continue

            # For romanised queries: skip results that are clearly non-Arabic
            # (e.g., Hindi, Yoruba, etc. returned for similar-sounding romanised text).
            # Arabic songs on YTMusic often have romanised English titles, so we
            # only skip when the title contains characters from non-Latin/non-Arabic
            # scripts (Devanagari, CJK, etc.) as a safe heuristic.
            if not query_is_arabic and orig_is_arabic:
                combined = title + " " + art
                non_latin_non_arabic = sum(
                    1 for c in combined
                    if ord(c) > 0x0900  # Devanagari, CJK, etc. — not Latin/Arabic
                    and not ("\u0600" <= c <= "\u06ff")  # exclude Arabic script
                )
                if non_latin_non_arabic > 3:
                    logger.debug(
                        f"[arabic][ytmusic] skip non-Arabic-language result "
                        f"for rom query: {title!r}"
                    )
                    continue

            seen_vids.add(vid)
            logger.debug(
                f"[arabic][ytmusic] q={query!r}  title={title!r}  "
                f"artist={art!r}  vid={vid}"
            )

            try:
                _ytm_executor = ThreadPoolExecutor(max_workers=1)
                try:
                    wp = _ytm_executor.submit(
                        yt.get_watch_playlist, videoId=vid, limit=1
                    ).result(timeout=6)
                except FuturesTimeoutError:
                    logger.debug(
                        f"[arabic][ytmusic] get_watch_playlist timeout vid={vid}"
                    )
                    _ytm_executor.shutdown(wait=False)
                    continue
                finally:
                    _ytm_executor.shutdown(wait=False)

                lyrics_id = wp.get("lyrics", "") if wp else ""
                if not lyrics_id:
                    logger.debug(f"[arabic][ytmusic] no lyrics browseId for vid={vid}")
                    continue

                _ytm_executor2 = ThreadPoolExecutor(max_workers=1)
                try:
                    lyr_data = _ytm_executor2.submit(
                        yt.get_lyrics, lyrics_id
                    ).result(timeout=6)
                except FuturesTimeoutError:
                    logger.debug(
                        f"[arabic][ytmusic] get_lyrics timeout lyrics_id={lyrics_id}"
                    )
                    _ytm_executor2.shutdown(wait=False)
                    continue
                finally:
                    _ytm_executor2.shutdown(wait=False)

                if not lyr_data:
                    continue
                text = (lyr_data.get("lyrics", "") or "").strip()
                if len(text) <= 50:
                    continue

                if _validate_arabic_lyrics(text, artist, song):
                    logger.info(
                        f"[arabic][ytmusic] candidate OK: {artist!r} - {song!r} "
                        f"vid={vid} len={len(text)}"
                    )
                    found.append((text, "ytmusic"))
                    arabic_found_count += 1
                    if len(found) >= 2:
                        return found
                else:
                    logger.debug(f"[arabic][ytmusic] REJECTED vid={vid} (quality check)")

            except Exception as inner_e:
                logger.debug(f"[arabic][ytmusic] error for vid={vid}: {inner_e}")

    return found


def _ytmusic_lyrics(artist: str, song: str) -> Optional[str]:
    """Convenience wrapper — returns the first valid YTMusic candidate or None."""
    cands = _ytmusic_candidates(artist, song)
    return cands[0][0] if cands else None


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LAYER 3: Genius lyrics fetch (NOT used for identity)
# ════════════════════════════════════════════════════════════════════════════

_GENIUS_NOISE_RE   = re.compile(
    r"(You might also like|See .+? lyrics|^\d+\s*Embed$|Embed$)",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_HDR_RE    = re.compile(r"^\[.*?\]$", re.MULTILINE)


def _clean_genius_lyrics(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r", "")
    text = _GENIUS_NOISE_RE.sub("", text)
    text = _SECTION_HDR_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _genius_search_hits(query: str) -> List[Dict]:
    if not _GENIUS_KEY:
        return []
    try:
        r = _ar_session.get(
            _GENIUS_SEARCH,
            params={"q": query, "per_page": 10},
            headers={"Authorization": f"Bearer {_GENIUS_KEY}"},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json().get("response", {}).get("hits", [])
    except Exception as e:
        logger.debug(f"[arabic][genius] search failed (q={query!r}): {e}")
    return []


def _genius_scrape_lyrics(song_url: str) -> Optional[str]:
    """Scrape lyrics from a Genius song page."""
    try:
        from bs4 import BeautifulSoup
        r = _ar_session.get(song_url, timeout=9)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not containers:
            return None
        parts = []
        for c in containers:
            for br in c.find_all("br"):
                br.replace_with("\n")
            parts.append(c.get_text())
        lyrics = _clean_genius_lyrics("\n".join(parts))
        return lyrics if len(lyrics) > 50 else None
    except Exception as e:
        logger.debug(f"[arabic][genius] scrape failed ({song_url}): {e}")
        return None


def _genius_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Fetch lyrics from Genius using multiple query strategies (Arabic → romanized →
    title-only) to maximise discovery.  Deduplicates URLs across queries.
    """
    rom_artist = _romanize(artist)
    rom_song   = _romanize(song)
    norm_song  = normalize_arabic(song)

    queries: List[str] = [f"{artist} {song}"]
    if rom_artist and rom_song:
        queries.append(f"{rom_artist} {rom_song}")
    if norm_song != song:
        queries.append(f"{artist} {norm_song}")
    if rom_song:
        queries.append(rom_song)

    seen_urls: set = set()
    for query in queries:
        hits = _genius_search_hits(query)
        if not hits:
            continue
        for hit in hits:
            if hit.get("type") != "song":
                continue
            res       = hit.get("result", {})
            cand_song = res.get("title", "")
            song_url  = res.get("url", "")
            if not song_url or song_url in seen_urls:
                continue
            seen_urls.add(song_url)
            if _is_non_original(cand_song):
                continue
            lyrics = _genius_scrape_lyrics(song_url)
            if lyrics:
                logger.info(
                    f"[arabic][genius] lyrics found for {artist!r} - {song!r} "
                    f"via query {query!r}"
                )
                return lyrics
    return None


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LAYER 4: lrclib fallback lyrics (Arabic-mode dedicated calls)
# ════════════════════════════════════════════════════════════════════════════

_LRC_TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}(?:\.\d+)?\]")


def _strip_lrc_timestamps(text: str) -> str:
    """Strip LRC-format timestamps like [00:32.75] from lyrics."""
    if not text:
        return text
    lines = []
    for line in text.splitlines():
        line = _LRC_TIMESTAMP_RE.sub("", line).strip()
        lines.append(line)
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _lrclib_direct(artist: str, song: str) -> Optional[str]:
    try:
        r = _ar_session.get(
            _LRCLIB_GET,
            params={"artist_name": artist, "track_name": song},
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            lyrics = data.get("plainLyrics", "") or ""
            # Fallback to synced lyrics if no plain lyrics available
            if not lyrics:
                lyrics = data.get("syncedLyrics", "") or ""
            lyrics = _strip_lrc_timestamps(lyrics)
            if lyrics and len(lyrics) > 30:
                logger.info(f"[arabic][lrclib] direct hit: {artist!r} - {song!r}")
                return lyrics
    except Exception as e:
        logger.debug(f"[arabic][lrclib] direct failed ({artist!r}, {song!r}): {e}")
    return None


def _lrclib_search_lyrics(artist: str, song: str) -> Optional[str]:
    try:
        r = _ar_session.get(
            _LRCLIB_SEARCH,
            params={"q": f"{artist} {song}"},
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            if not isinstance(data, list):
                return None
            for item in data:
                lyrics = item.get("plainLyrics", "") or ""
                if not lyrics:
                    lyrics = item.get("syncedLyrics", "") or ""
                lyrics = _strip_lrc_timestamps(lyrics)
                if not lyrics or len(lyrics) <= 30:
                    continue
                if _is_non_original(item.get("trackName", "")):
                    continue
                logger.info(f"[arabic][lrclib] search hit: {artist!r} - {song!r}")
                return lyrics
    except Exception as e:
        logger.debug(f"[arabic][lrclib] search failed ({artist!r}, {song!r}): {e}")
    return None


def _lrclib_lyrics(artist: str, song: str) -> Optional[str]:
    lyrics = _lrclib_direct(artist, song)
    if lyrics:
        return lyrics
    return _lrclib_search_lyrics(artist, song)


# ════════════════════════════════════════════════════════════════════════════
# ANGHAMI — On-demand per-request helpers (no crawling, no indexing)
# ════════════════════════════════════════════════════════════════════════════


def _is_anghami_cf_blocked(response_text: str) -> bool:
    """
    Return True if Anghami served an Access Denied / CloudFront error page.
    Real lyrics pages are 30–80 KB; error pages are < 2 KB.
    """
    if len(response_text) > 2000:
        return False
    lower = response_text.lower()
    return "access denied" in lower or "cloudfront" in lower or len(response_text) < 1600


def _anghami_api_find_id(artist: str, song: str) -> Optional[int]:
    """
    Use Anghami's search API to find the song_id for an artist/song pair.
    Purely per-request — no crawling, no database, no background threads.
    Anghami's REST v4 API returns XML; this parses song IDs out of it.
    """
    import xml.etree.ElementTree as _ET_local
    queries = [f"{artist} {song}"]
    rom = f"{_romanize(artist)} {_romanize(song)}".strip()
    if rom and rom != queries[0]:
        queries.append(rom)

    for query in queries:
        try:
            r = _ar_session.get(
                _ANGHAMI_API_SEARCH,
                params={"query": query, "type": "songs", "forceloginaccess": 1},
                timeout=7,
            )
            if r.status_code != 200 or not r.text.strip():
                continue
            # API returns XML — skip if status=failed (requires auth or empty result)
            if 'status="failed"' in r.text or "status='failed'" in r.text:
                logger.debug(f"[arabic][anghami_api] auth required for {query!r}")
                break
            # Try to parse XML and pull the first song id attribute
            root = _ET_local.fromstring(r.text)
            for el in root.iter("song"):
                sid = el.get("id") or el.get("song_id")
                if sid and sid.isdigit():
                    logger.debug(
                        f"[arabic][anghami_api] found id={sid} "
                        f"for {artist!r} - {song!r}"
                    )
                    return int(sid)
        except Exception as e:
            logger.debug(f"[arabic][anghami_api] query {query!r} error: {e}")
    return None


def _anghami_lyrics_by_id(song_id: int, artist: str, song: str) -> Optional[str]:
    """Fetch and extract lyrics directly from a known kalimat.anghami.com song ID."""
    url = _ANGHAMI_LYRICS_BASE.format(song_id)
    logger.debug(f"[arabic][anghami_direct] fetching id={song_id}")
    return _scrape_url_for_lyrics(url, artist, song)


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — TARGETED SCRAPERS (Layers 3b and 5b)
# ════════════════════════════════════════════════════════════════════════════


def _ddg_find_first_url(query: str, domain_filter: Optional[str] = None) -> Optional[str]:
    """
    Send a DuckDuckGo HTML search and return the first result URL that
    belongs to `domain_filter` (substring match).  If no filter is given,
    returns the first non-DDG URL.  Used internally by the targeted scrapers.
    """
    import time
    for attempt in range(2):
        try:
            from bs4 import BeautifulSoup
            r = _ar_session.post(
                _DDG_SEARCH_URL,
                data={"q": query},
                headers={"Accept-Language": "ar,en;q=0.9"},
                timeout=6,
            )
            if r.status_code == 202:
                # DDG anti-bot hold — retry once after brief pause
                logger.debug(f"[arabic][ddg_find] 202 on attempt {attempt+1}, retrying")
                if attempt == 0:
                    time.sleep(1)
                    continue
                return None
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http") or "duckduckgo.com" in href:
                    continue
                if domain_filter and domain_filter not in href:
                    continue
                return href
        except Exception as e:
            logger.debug(f"[arabic][ddg_find] failed for {query!r}: {e}")
            break
    return None


def _anghami_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Layer 3b — Anghami kalimat (kalimat.anghami.com).

    On-demand, per-request — no background indexing, no database.

    Two-stage fetch:
    1. Anghami search API → get song_id → fetch kalimat lyrics page directly.
    2. DDG site: search fallback (may be rate-limited from Replit).
    """
    # ── 1. Anghami API → direct page fetch ────────────────────────────────────
    song_id = _anghami_api_find_id(artist, song)
    if song_id:
        lyr = _anghami_lyrics_by_id(song_id, artist, song)
        if lyr:
            logger.info(
                f"[arabic][anghami] API hit: id={song_id} "
                f"{artist!r} - {song!r}"
            )
            return lyr

    # ── 2. DDG site: search fallback ──────────────────────────────────────────
    for q in [
        f"site:kalimat.anghami.com {artist} {song}",
        f"site:kalimat.anghami.com {_romanize(artist)} {_romanize(song)}",
    ]:
        url = _ddg_find_first_url(q, domain_filter="kalimat.anghami.com")
        if not url:
            continue
        logger.debug(f"[arabic][anghami] DDG found URL: {url[:80]}")
        lyr = _scrape_url_for_lyrics(url, artist, song)
        if lyr:
            return lyr
    return None


def _aghanilyrics_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Layer 5b — aghanilyrics.com.

    Uses a DDG site: search to find the songlyrics.php URL, then fetches it
    directly with the required Referer header (the site returns a 200 but with
    an error body without it).  Extracts lyrics from known CSS selectors.
    """
    query = f"site:aghanilyrics.com {artist} {song}"
    url   = _ddg_find_first_url(query, domain_filter="aghanilyrics.com")
    if not url:
        logger.debug(f"[arabic][aghanilyrics] no URL for {artist!r} - {song!r}")
        return None

    logger.debug(f"[arabic][aghanilyrics] scraping {url[:80]}")
    try:
        from bs4 import BeautifulSoup
        r = _ar_session.get(
            url,
            timeout=9,
            headers={"Referer": "https://www.aghanilyrics.com/"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        for selector in _AGHANILYRICS_SELECTORS:
            try:
                el = soup.select_one(selector)
            except Exception:
                el = None
            if not el:
                continue
            raw = el.get_text(separator="\n")
            ar_count = sum(1 for c in raw if "\u0600" <= c <= "\u06ff")
            if ar_count < 80:
                continue
            lines = [
                ln.strip() for ln in raw.split("\n")
                if ln.strip() and sum(1 for c in ln if "\u0600" <= c <= "\u06ff") >= 2
                and "كلمات" not in ln  # strip page-title lines
            ]
            candidate = "\n".join(lines)
            if _validate_arabic_lyrics(candidate, artist, song):
                logger.info(
                    f"[arabic][aghanilyrics] OK: {artist!r} - {song!r} len={len(candidate)}"
                )
                return candidate
    except Exception as e:
        logger.debug(f"[arabic][aghanilyrics] scrape failed: {e}")
    return None


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LAYER D: General DuckDuckGo search + web scrape (last resort)
# ════════════════════════════════════════════════════════════════════════════

# CSS selectors tried in order on every scraped page.
# Tuple: (label, selector) — label is for debug only.
_DDG_LYRICS_SELECTORS = [
    ("anghami-body",   "div[class*=lyrics_body]"),
    ("anghami-page",   "div[class*=lyrics_page_container]"),
    ("aghani-w3ar",    "div.w3-display-container.w3-center.w3-ar"),
    ("entry-content",  "div.entry-content"),
    ("post-content",   "div.post-content"),
    ("lyrics-div",     "div.lyrics"),
    ("lyric-div",      "div.lyric"),
    ("song-lyrics",    "div.song-lyrics"),
    ("article",        "article"),
]


def _scrape_url_for_lyrics(url: str, artist: str, song: str) -> Optional[str]:
    """
    Fetch a URL and extract Arabic lyrics from its HTML.
    Tries known CSS selectors first, then falls back to the largest Arabic text
    block on the page.  Applies _validate_arabic_lyrics() before returning.
    """
    try:
        from bs4 import BeautifulSoup
        r = _ar_session.get(url, timeout=9, allow_redirects=True)
        if r.status_code != 200:
            return None
        # Bail out fast when Anghami's CloudFront is returning error pages
        if "anghami.com" in url and _is_anghami_cf_blocked(r.text):
            logger.debug(f"[arabic][scrape] CloudFront block for {url[:60]}")
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form"]):
            tag.decompose()

        # ── Try known selectors ───────────────────────────────────────────────
        for label, selector in _DDG_LYRICS_SELECTORS:
            try:
                el = soup.select_one(selector)
            except Exception:
                el = None
            if not el:
                continue
            raw = el.get_text(separator="\n")
            ar_count = sum(1 for c in raw if "\u0600" <= c <= "\u06ff")
            if ar_count < 80:
                continue
            # Keep only lines that carry Arabic content
            lines = [
                ln.strip() for ln in raw.split("\n")
                if ln.strip() and sum(1 for c in ln if "\u0600" <= c <= "\u06ff") >= 2
            ]
            candidate = "\n".join(lines)
            if _validate_arabic_lyrics(candidate, artist, song):
                logger.debug(
                    f"[arabic][layerD] selector={label!r} matched at {url[:60]}"
                )
                return candidate

        # ── Fallback: largest Arabic text block ───────────────────────────────
        best_text  = ""
        best_count = 0
        for div in soup.find_all(["div", "p", "article", "section"]):
            text = div.get_text(separator="\n")
            ar_lines = [
                ln.strip() for ln in text.split("\n")
                if len(ln.strip()) > 10
                and sum(1 for c in ln if "\u0600" <= c <= "\u06ff") > 5
            ]
            if len(ar_lines) > best_count:
                best_count = len(ar_lines)
                best_text  = "\n".join(ar_lines)

        if best_count >= 12 and _validate_arabic_lyrics(best_text, artist, song):
            logger.debug(
                f"[arabic][layerD] fallback block ({best_count} lines) at {url[:60]}"
            )
            return best_text

    except Exception as e:
        logger.debug(f"[arabic][layerD] scrape failed ({url[:60]}): {e}")
    return None


def _ddg_general_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Layer D: General DuckDuckGo HTML search for Arabic lyrics, then scrape results.

    This is the last-resort layer — only called when all targeted layers have
    failed to produce a high-confidence result.  Sends the query
    '{artist} {song} كلمات' to DuckDuckGo's HTML endpoint, extracts the top
    result URLs (skipping social/streaming domains), and tries
    _scrape_url_for_lyrics() on each until validated lyrics are found.
    """
    import time
    query = f"{artist} {song} كلمات"
    r = None
    for attempt in range(2):
        try:
            r = _ar_session.post(
                _DDG_SEARCH_URL,
                data={"q": query},
                headers={"Accept-Language": "ar,en;q=0.9"},
                timeout=9,
            )
            if r.status_code == 202:
                logger.debug(f"[arabic][layerD] DDG 202 on attempt {attempt+1}, retrying")
                if attempt == 0:
                    time.sleep(2)
                    r = None
                    continue
                return None
            if r.status_code != 200:
                logger.debug(f"[arabic][layerD] DDG returned {r.status_code}")
                return None
            break
        except Exception as _e:
            logger.debug(f"[arabic][layerD] DDG request failed: {_e}")
            return None
    if r is None:
        return None
    try:

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        # DuckDuckGo HTML returns result URLs directly in <a href="...">
        urls: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            if "duckduckgo.com" in href:
                continue
            # Derive the domain for skip-list check
            try:
                domain = href.split("/")[2].lower()
                domain = re.sub(r"^www\.", "", domain)
            except IndexError:
                continue
            if any(skip in domain for skip in _DDG_SKIP_DOMAINS):
                continue
            urls.append(href)

        # Deduplicate while preserving order
        seen: set = set()
        unique_urls: List[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        logger.debug(
            f"[arabic][layerD] DDG gave {len(unique_urls)} candidate URLs "
            f"for {artist!r} - {song!r}"
        )

        for url in unique_urls[:6]:
            logger.debug(f"[arabic][layerD] trying {url[:80]}")
            lyr = _scrape_url_for_lyrics(url, artist, song)
            if lyr:
                logger.info(
                    f"[arabic][layerD] lyrics found for {artist!r} - {song!r} "
                    f"via {url[:60]}"
                )
                return lyr

    except Exception as e:
        logger.debug(f"[arabic][layerD] DDG search failed: {e}")
    return None


# ════════════════════════════════════════════════════════════════════════════
# MAIN RESOLVER
# ════════════════════════════════════════════════════════════════════════════

def resolve_arabic_song(
    artist: str,
    song:   str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Two-phase Arabic resolver:

    Phase 1 — Identity via YouTube (Layers 1 → 2 → 5)
    Phase 2 — Lyrics via YouTube Music, Genius, then lrclib (Layers 2a → 3 → 4)

    Returns (resolved_artist, resolved_song, lyrics, yt_video_id).
    yt_video_id is the YouTube video ID of the confirmed song result — use it
    to build https://youtube.com/watch?v=<yt_video_id> for a direct watch link.
    All values are None on complete failure.
    NEVER falls back into any main bot service.
    """
    norm_artist = normalize_arabic(artist)
    norm_song   = normalize_arabic(song)
    rom_artist  = _romanize(artist)
    rom_song    = _romanize(song)

    # ── Phase 1: Identity resolution ─────────────────────────────────────────

    # Layer 1: YouTube with original Arabic text
    yt_result = _yt_resolve(artist, song, f"{artist} {song}")

    # Layer 2: YouTube with normalized Arabic text (if Layer 1 failed)
    if not yt_result and (norm_artist != artist or norm_song != song):
        yt_result = _yt_resolve(artist, song, f"{norm_artist} {norm_song}")

    # Layer 5: YouTube with romanized text (last resort, hidden from user)
    if not yt_result and rom_artist and rom_song and _has_arabic(artist):
        yt_result = _yt_resolve(artist, song, f"{rom_artist} {rom_song}")

    # If YouTube gave us nothing, synthesize identity from original input
    if not yt_result:
        logger.info(f"[arabic] YouTube identity resolution failed, trying lyrics directly")
        res_artist, res_song = artist, song
        eng_artist = eng_song = None
        yt_video_id: Optional[str] = None
        direct_only = True
    else:
        res_artist, res_song, eng_artist, eng_song, yt_video_id = yt_result
        direct_only = False

    logger.debug(f"[arabic] identity: {res_artist!r} - {res_song!r}  "
                 f"eng_alias: {eng_artist!r} - {eng_song!r}  vid={yt_video_id}")

    # ── Phase 2: Lyrics fetch ─────────────────────────────────────────────────

    def _fetch_lyrics(a: str, s: str) -> Optional[str]:
        """
        Collect lyrics from all layers, score every passing candidate, and
        return the highest-scoring result.

        Order: YTMusic (all valid) → Genius → Anghami → lrclib →
               aghanilyrics → general DDG (fallback only).

        Stops early if any candidate scores ≥ _HIGH_CONFIDENCE_SCORE.
        The final winner is chosen by score, NOT by arrival order.
        """
        candidates: List[Tuple[str, str, float]] = []  # (lyrics, source, score)

        def _add(lyr: Optional[str], source: str) -> float:
            """Validate, score, and register a candidate. Returns its score."""
            if not lyr or not _validate_arabic_lyrics(lyr, a, s):
                return 0.0
            sc = _score_lyrics_candidate(lyr, a, s, source)
            candidates.append((lyr, source, sc))
            logger.debug(
                f"[arabic][score] source={source!r} score={sc:.1f} len={len(lyr)}"
            )
            return sc

        # ── Layer 2a: YouTube Music — collect ALL valid candidates ────────────
        for lyr_text, src in _ytmusic_candidates(a, s):
            sc = _add(lyr_text, src)
            if sc >= _HIGH_CONFIDENCE_SCORE:
                logger.info(
                    f"[arabic][fetch] early stop: ytmusic score={sc:.1f}"
                )
                return lyr_text

        # ── Layer 3: Genius ───────────────────────────────────────────────────
        sc = _add(_genius_lyrics(a, s), "genius")
        if sc >= _HIGH_CONFIDENCE_SCORE:
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[0][0]

        # ── Layer 3b: Anghami kalimat (targeted) ─────────────────────────────
        sc = _add(_anghami_lyrics(a, s), "anghami")
        if sc >= _HIGH_CONFIDENCE_SCORE:
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[0][0]

        # ── Layer 4: lrclib ───────────────────────────────────────────────────
        _add(_lrclib_lyrics(a, s), "lrclib")

        # ── Layer 5b: aghanilyrics (targeted, requires Referer) ───────────────
        _add(_aghanilyrics_lyrics(a, s), "aghanilyrics")

        # ── Layer D: General DDG — only if still no high-quality result ───────
        best_so_far = max((c[2] for c in candidates), default=0.0)
        if best_so_far < 50.0:
            _add(_ddg_general_lyrics(a, s), "web")

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[2], reverse=True)
        winner = candidates[0]
        logger.info(
            f"[arabic][fetch] winner: source={winner[1]!r} "
            f"score={winner[2]:.1f} len={len(winner[0])}"
        )
        return winner[0]

    # Primary attempt: YouTube-resolved Arabic identity
    lyrics = _fetch_lyrics(res_artist, res_song)

    # English alias from bilingual YouTube title (e.g. "Majid Al Mohandis", "Dayea")
    # YouTube Music often indexes Arabic-language songs under the English artist name
    if not lyrics and eng_artist and eng_song:
        logger.debug(f"[arabic] trying English alias: {eng_artist!r} - {eng_song!r}")
        lyrics = _fetch_lyrics(eng_artist, eng_song)

    # If identity differed from input, also try original Arabic names
    if not lyrics and (res_artist != artist or res_song != song):
        lyrics = _fetch_lyrics(artist, song)

    # If direct_only mode, also try normalized forms
    if not lyrics and direct_only:
        lyrics = _fetch_lyrics(norm_artist, norm_song)

    # Final romanized attempt (poor quality but worth a shot)
    if not lyrics and rom_artist and rom_song and _has_arabic(artist):
        lyrics = _fetch_lyrics(rom_artist, rom_song)

    if not lyrics:
        logger.info(f"[arabic] no lyrics found for {artist!r} - {song!r}")
        return None, None, None, None

    logger.info(f"[arabic] resolved: {res_artist!r} - {res_song!r}  vid={yt_video_id}")
    return res_artist, res_song, lyrics, yt_video_id
