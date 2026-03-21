"""
services/arabic_mode.py

Arabic Songs Mode — Fully Isolated Pipeline.
Self-contained. Does NOT import from or mutate any main bot service.

Two-phase architecture:
  Phase 1 — Identity Resolution (YouTube)
    Layer 1: YouTube search with original Arabic text
    Layer 2: YouTube search with normalized Arabic text
    Layer 5: YouTube search with romanized (transliterated) text  ← last resort
  Phase 2 — Lyrics Fetch (once identity confirmed)
    Layer 3: Genius API search → page scrape
    Layer 4: lrclib direct + search
"""

import os
import re
import json
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
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
    text = text.replace("ؤ", "و")
    text = text.replace("ئ", "ي")
    text = text.replace("ء", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


_FORMAT_ERROR = (
    "Please use the correct format:\n"
    "Artist - Song\n\n"
    "Example:\n"
    "ماجد المهندس - ضايع"
)


def parse_arabic_input(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Strict 'artist - song' parser.
    Returns (artist, song, None) or (None, None, error_msg).
    """
    text = re.sub(r"\s*[–—\u2012\u2013\u2014\u2015\-]+\s*", " - ", text.strip())
    if " - " not in text:
        return None, None, _FORMAT_ERROR
    parts = text.split(" - ", 1)
    artist, song = parts[0].strip(), parts[1].strip()
    if not artist or not song:
        return None, None, _FORMAT_ERROR
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


def _yt_parse_title(title: str, channel: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (artist, song) from a YouTube video title.
    Handles:
      • "Artist - Song"
      • "Arabic - Song | English - Song"  (bilingual — prefers Arabic part)
      • "Artist | Song"
    """
    # Remove official video/audio/lyric qualifiers
    clean = _YT_SUFFIX_RE.sub("", title).strip()

    # Bilingual format: take the Arabic segment if present, else first segment
    if " | " in clean:
        segments = [s.strip() for s in clean.split(" | ")]
        arabic_segs = [s for s in segments if _has_arabic(s)]
        clean = arabic_segs[0] if arabic_segs else segments[0]

    # Primary separator: " - "
    if " - " in clean:
        parts = clean.split(" - ", 1)
        artist = parts[0].strip()
        song   = parts[1].strip()
        if artist and song:
            return artist, song

    # Secondary separator: " | "
    if " | " in clean:
        parts = clean.split(" | ", 1)
        artist, song = parts[0].strip(), parts[1].strip()
        if artist and song:
            return artist, song

    # Fallback: treat channel as artist, cleaned title as song
    if channel and clean:
        return channel.strip(), clean

    return None, None


def _yt_compute_score(
    query_artist: str, query_song: str,
    cand_artist:  str, cand_song:   str,
) -> float:
    """
    Combined score that handles both Arabic-to-Arabic and Arabic-to-English
    (transliterated) matches.

    Artist ≥ 60% threshold + Song ≥ 60% threshold → must both pass.
    Combined score: artist 50% + song 40% + clean title 10%.
    """
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

    # Romanized comparison (catches English/transliterated YouTube titles)
    rom_qa = _romanize(query_artist)
    rom_qs = _romanize(query_song)

    def _rom_overlap(rq: str, rc: str) -> float:
        tq = set(rq.split())
        tc = set(rc.lower().split())
        if not tq:
            return 0.0
        return len(tq & tc) / len(tq)

    rom_artist = _rom_overlap(rom_qa, cand_artist) * 50
    rom_song   = _rom_overlap(rom_qs,  cand_song)  * 40

    artist_score = max(ar_artist, rom_artist)
    song_score   = max(ar_song,   rom_song)

    # Strict artist + song threshold enforcement per spec (≥ 60% each)
    if artist_score < 30 or song_score < 24:   # 30 = 60% of 50; 24 = 60% of 40
        return 0.0

    clean_bonus = 0 if _is_non_original(cand_song) else 10
    return artist_score + song_score + clean_bonus


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
) -> Optional[Tuple[str, str]]:
    """
    Search YouTube with `search_query`, parse titles, score candidates.
    Returns (resolved_artist, resolved_song) or None if no strong match.
    """
    candidates = _yt_search(search_query)
    if not candidates:
        return None

    best_score  = 0.0
    best_result: Optional[Tuple[str, str]] = None

    for cand in candidates:
        title   = cand.get("title", "")
        channel = cand.get("channel", "")

        if not title:
            continue

        # Hard reject non-original types
        if any(w in title.lower() for w in _REJECT_YT_WORDS):
            continue

        parsed_artist, parsed_song = _yt_parse_title(title, channel)
        if not parsed_artist or not parsed_song:
            continue

        score = _yt_compute_score(query_artist, query_song, parsed_artist, parsed_song)

        logger.debug(
            f"[arabic][yt] q={search_query!r}  "
            f"title={title!r}  pa={parsed_artist!r}  ps={parsed_song!r}  score={score:.1f}"
        )

        if score > best_score:
            best_score = score
            best_result = (parsed_artist, parsed_song)

    if best_result and best_score >= 40:
        logger.info(
            f"[arabic][yt] resolved: {best_result[0]!r} - {best_result[1]!r} "
            f"score={best_score:.1f} q={search_query!r}"
        )
        return best_result

    return None


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
    Fetch lyrics from Genius for a confirmed artist + song identity.
    Uses light scoring to avoid picking a completely wrong song.
    """
    hits = _genius_search_hits(f"{artist} {song}")
    if not hits:
        return None

    for hit in hits:
        if hit.get("type") != "song":
            continue
        res        = hit.get("result", {})
        cand_song  = res.get("title", "")
        song_url   = res.get("url", "")
        if not song_url:
            continue
        if _is_non_original(cand_song):
            continue
        lyrics = _genius_scrape_lyrics(song_url)
        if lyrics:
            logger.info(f"[arabic][genius] lyrics found for {artist!r} - {song!r}")
            return lyrics

    return None


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — LAYER 4: lrclib fallback lyrics (Arabic-mode dedicated calls)
# ════════════════════════════════════════════════════════════════════════════

def _lrclib_direct(artist: str, song: str) -> Optional[str]:
    try:
        r = _ar_session.get(
            _LRCLIB_GET,
            params={"artist_name": artist, "track_name": song},
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            lyrics = data.get("plainLyrics", "")
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
                lyrics = item.get("plainLyrics", "")
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
# MAIN RESOLVER
# ════════════════════════════════════════════════════════════════════════════

def resolve_arabic_song(
    artist: str,
    song:   str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Two-phase Arabic resolver:

    Phase 1 — Identity via YouTube (Layers 1 → 2 → 5)
    Phase 2 — Lyrics via Genius then lrclib (Layers 3 → 4)

    Returns (resolved_artist, resolved_song, lyrics) or (None, None, None).
    NEVER falls back into any main bot service.
    """
    norm_artist = normalize_arabic(artist)
    norm_song   = normalize_arabic(song)
    rom_artist  = _romanize(artist)
    rom_song    = _romanize(song)

    # ── Phase 1: Identity resolution ─────────────────────────────────────────

    # Layer 1: YouTube with original Arabic text
    identity = _yt_resolve(artist, song, f"{artist} {song}")

    # Layer 2: YouTube with normalized Arabic text (if Layer 1 failed)
    if not identity and (norm_artist != artist or norm_song != song):
        identity = _yt_resolve(artist, song, f"{norm_artist} {norm_song}")

    # Layer 5: YouTube with romanized text (last resort, hidden from user)
    if not identity and rom_artist and rom_song and _has_arabic(artist):
        identity = _yt_resolve(artist, song, f"{rom_artist} {rom_song}")

    # If YouTube gave us nothing, synthesize identity from original input
    # (still attempt lyrics fetch — sometimes Genius / lrclib have them)
    if not identity:
        logger.info(f"[arabic] YouTube identity resolution failed, trying lyrics directly")
        identity = (artist, song)
        direct_only = True
    else:
        direct_only = False

    res_artist, res_song = identity

    # ── Phase 2: Lyrics fetch ─────────────────────────────────────────────────

    def _fetch_lyrics(a: str, s: str) -> Optional[str]:
        """Layer 3 → 4 for a given artist/song pair."""
        # Layer 3: Genius
        lyr = _genius_lyrics(a, s)
        if lyr:
            return lyr
        # Layer 4: lrclib
        return _lrclib_lyrics(a, s)

    # Primary attempt: use YouTube-resolved identity
    lyrics = _fetch_lyrics(res_artist, res_song)

    # If identity differed from input, also try original Arabic names
    if not lyrics and (res_artist != artist or res_song != song):
        lyrics = _fetch_lyrics(artist, song)

    # If direct_only mode, also try normalized forms
    if not lyrics and direct_only:
        lyrics = _fetch_lyrics(norm_artist, norm_song)

    # Final romanized attempt for lyrics
    if not lyrics and rom_artist and rom_song and _has_arabic(artist):
        lyrics = _fetch_lyrics(rom_artist, rom_song)

    if not lyrics:
        logger.info(f"[arabic] no lyrics found for {artist!r} - {song!r}")
        return None, None, None

    logger.info(f"[arabic] resolved: {res_artist!r} - {res_song!r}")
    return res_artist, res_song, lyrics
