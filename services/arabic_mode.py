"""
services/arabic_mode.py

Arabic Songs Mode — Fully Isolated Pipeline.
Self-contained subsystem. Does NOT modify or mutate any main bot logic.

Search hierarchy (Arabic-dedicated, NOT the main bot resolver):
  Layer 1 — Genius API search with original Arabic text
  Layer 2 — Genius API search with normalized Arabic text       (parallel with L1)
  Layer 3 — lrclib direct + search with original/normalized     (parallel fallback)
  Layer 4 — Romanized transliteration fallback (hidden, last resort)
"""

import os
import re
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

# ── Dedicated HTTP session for Arabic mode only ───────────────────────────────

_ar_session = requests.Session()
_ar_session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LyricsBotAR/1.0)"})

_GENIUS_KEY = os.environ.get("GENIUS_API_KEY", "")
_GENIUS_SEARCH_URL = "https://api.genius.com/search"
_LRCLIB_GET_URL    = "https://lrclib.net/api/get"
_LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"

# ── Arabic normalization ──────────────────────────────────────────────────────

_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_TATWEEL_RE    = re.compile(r"\u0640")
_DASH_RE       = re.compile(r"[–—\u2012\u2013\u2014\u2015\u002D]")


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for search matching.
    Returns a cleaned COPY; the original display text is never overwritten.
    """
    text = _DASH_RE.sub(" ", text)
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


# ── Input parsing ─────────────────────────────────────────────────────────────

_FORMAT_ERROR = (
    "Please use the correct format:\n"
    "Artist - Song\n\n"
    "Example:\n"
    "ماجد المهندس - ضايع"
)

_INPUT_DASH_RE = re.compile(r"\s*[–—\u2012\u2013\u2014\u2015\-]+\s*")


def parse_arabic_input(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Strictly parse 'artist - song' format.
    Returns (artist, song, None) on success, or (None, None, error_msg) on failure.
    """
    text = text.strip()
    # Normalize any dash variant to " - "
    text = re.sub(r"\s*[–—\u2012\u2013\u2014\u2015]+\s*", " - ", text)
    if " - " not in text:
        return None, None, _FORMAT_ERROR
    parts = text.split(" - ", 1)
    artist = parts[0].strip()
    song   = parts[1].strip()
    if not artist or not song:
        return None, None, _FORMAT_ERROR
    return artist, song, None


# ── Hard filter ───────────────────────────────────────────────────────────────

_REJECT_WORDS = frozenset([
    "remix", "live", "cover", "karaoke", "slowed", "sped up",
    "reverb", "instrumental", "acoustic", "tribute", "mashup",
])


def _is_non_original(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in _REJECT_WORDS)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _ar_token_set(text: str) -> set:
    """Tokens from both original and normalized form, for maximum match surface."""
    norm = normalize_arabic(text)
    tokens = set(norm.split()) | set(text.lower().split())
    return {t for t in tokens if len(t) > 1}


def _token_overlap(query: str, candidate: str) -> float:
    qt = _ar_token_set(query)
    ct = _ar_token_set(candidate)
    if not qt:
        return 0.0
    return len(qt & ct) / len(qt)


def _score(query_artist: str, query_song: str, cand_artist: str, cand_song: str) -> float:
    """Score 0–100: artist 50%, song 40%, clean title 10%."""
    a = _token_overlap(query_artist, cand_artist) * 50
    s = _token_overlap(query_song,   cand_song)   * 40
    c = 0 if _is_non_original(cand_song) else 10
    return a + s + c


# ── Lyrics cleaning ───────────────────────────────────────────────────────────

_GENIUS_NOISE_RE = re.compile(
    r"(You might also like|See.*?lyrics|.*?Lyrics$|^\d+\s*Embed$|Embed$)",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_HEADER_RE = re.compile(r"^\[.*?\]$", re.MULTILINE)


def _clean_genius_lyrics(lyrics: str) -> str:
    if not lyrics:
        return ""
    lyrics = lyrics.replace("\r", "")
    lyrics = _GENIUS_NOISE_RE.sub("", lyrics)
    lyrics = _SECTION_HEADER_RE.sub("", lyrics)
    lyrics = re.sub(r"\n{3,}", "\n\n", lyrics)
    return lyrics.strip()


# ── Layer 1 & 2: Genius search + lyrics scrape ────────────────────────────────

def _genius_search_hits(query: str) -> List[Dict]:
    """Hit the Genius search API and return raw hit list (up to 10)."""
    if not _GENIUS_KEY:
        return []
    try:
        r = _ar_session.get(
            _GENIUS_SEARCH_URL,
            params={"q": query, "per_page": 10},
            headers={"Authorization": f"Bearer {_GENIUS_KEY}"},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json().get("response", {}).get("hits", [])
    except Exception as e:
        logger.debug(f"[arabic] genius search failed (q={query!r}): {e}")
    return []


def _genius_scrape_lyrics(song_url: str) -> Optional[str]:
    """Scrape lyrics from a Genius song page using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
        r = _ar_session.get(
            song_url,
            timeout=8,
        )
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
        lyrics = "\n".join(parts)
        lyrics = _clean_genius_lyrics(lyrics)
        return lyrics if len(lyrics) > 50 else None
    except Exception as e:
        logger.debug(f"[arabic] genius scrape failed ({song_url}): {e}")
        return None


def _genius_find(
    query_artist: str,
    query_song:   str,
    search_query: str,
) -> Optional[Tuple[str, str, str]]:
    """
    Search Genius with `search_query`, score all hits against the original
    query_artist + query_song, scrape lyrics for the best candidate.
    Returns (resolved_artist, resolved_song, lyrics) or None.
    """
    hits = _genius_search_hits(search_query)
    if not hits:
        return None

    best_score  = -1.0
    best_result = None

    for hit in hits:
        if hit.get("type") != "song":
            continue
        res = hit.get("result", {})
        cand_artist = res.get("primary_artist", {}).get("name", "")
        cand_song   = res.get("title", "")
        song_url    = res.get("url", "")

        if not cand_artist or not cand_song or not song_url:
            continue

        if _is_non_original(cand_song):
            continue

        score = _score(query_artist, query_song, cand_artist, cand_song)
        logger.debug(
            f"[arabic] genius hit: {cand_artist!r} - {cand_song!r} score={score:.1f} q={search_query!r}"
        )
        if score > best_score:
            best_score = score
            best_result = (cand_artist, cand_song, song_url)

    if best_result is None or best_score < 15:
        return None

    cand_artist, cand_song, song_url = best_result
    lyrics = _genius_scrape_lyrics(song_url)
    if not lyrics:
        return None

    logger.info(
        f"[arabic] genius found: {cand_artist!r} - {cand_song!r} "
        f"score={best_score:.1f} q={search_query!r}"
    )
    return cand_artist, cand_song, lyrics


# ── Layer 3: lrclib (dedicated Arabic path) ───────────────────────────────────

def _lrclib_direct(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    try:
        r = _ar_session.get(
            _LRCLIB_GET_URL,
            params={"artist_name": artist, "track_name": song},
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            lyrics = data.get("plainLyrics", "")
            if lyrics and len(lyrics) > 30:
                return data.get("artistName", artist), data.get("trackName", song), lyrics
    except Exception as e:
        logger.debug(f"[arabic] lrclib direct failed ({artist!r}, {song!r}): {e}")
    return None


def _lrclib_search(query: str, expected_artist: str = "") -> Optional[Tuple[str, str, str]]:
    try:
        r = _ar_session.get(
            _LRCLIB_SEARCH_URL,
            params={"q": query},
            timeout=3,
        )
        if r.status_code == 200:
            data = r.json()
            if not isinstance(data, list) or not data:
                return None
            best_score  = -1.0
            best_result = None
            for item in data:
                lyrics = item.get("plainLyrics", "")
                if not lyrics or len(lyrics) <= 30:
                    continue
                ra = item.get("artistName", "")
                rs = item.get("trackName",  "")
                if _is_non_original(rs):
                    continue
                score = _score(expected_artist, query.replace(expected_artist, "").strip(), ra, rs)
                if expected_artist:
                    if _ar_token_set(expected_artist) & _ar_token_set(ra):
                        score += 20
                    else:
                        score -= 20
                if score > best_score:
                    best_score = score
                    best_result = (ra, rs, lyrics)
            return best_result
    except Exception as e:
        logger.debug(f"[arabic] lrclib search failed (q={query!r}): {e}")
    return None


def _try_lrclib(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    """Try lrclib direct then search."""
    r = _lrclib_direct(artist, song)
    if r:
        return r
    norm_artist = normalize_arabic(artist)
    norm_song   = normalize_arabic(song)
    if norm_artist != artist or norm_song != song:
        r = _lrclib_direct(norm_artist, norm_song)
        if r:
            return r
    r = _lrclib_search(f"{artist} {song}", expected_artist=artist)
    if r:
        return r
    return None


# ── Layer 4: Romanized transliteration (hidden fallback) ─────────────────────

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


def _has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


# ── Candidate collector ───────────────────────────────────────────────────────

def _make_candidate(result: Optional[Tuple[str, str, str]], src: str,
                    query_artist: str, query_song: str) -> Optional[Dict]:
    if not result:
        return None
    ra, rs, rl = result
    score = _score(query_artist, query_song, ra, rs)
    if _is_non_original(rs):
        score -= 40
    return {"artist": ra, "song": rs, "lyrics": rl, "score": score, "source": src}


# ── Main resolver ─────────────────────────────────────────────────────────────

def resolve_arabic_song(
    artist: str,
    song:   str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Multi-layer dedicated Arabic resolver.

    Layer 1 — Genius original Arabic text
    Layer 2 — Genius normalized Arabic text       (parallel with L1)
    Layer 3 — lrclib original + normalized        (parallel fallback)
    Layer 4 — Genius romanized fallback           (hidden, last resort)

    Returns (resolved_artist, resolved_song, lyrics) or (None, None, None).
    NEVER falls back into the main bot resolver.
    """
    norm_artist = normalize_arabic(artist)
    norm_song   = normalize_arabic(song)
    rom_artist  = _romanize(artist)
    rom_song    = _romanize(song)

    candidates: List[Dict] = []

    # ── Phase 1: Genius L1 + L2 + lrclib in parallel ─────────────────────────
    _phase1 = {
        "genius-original":   (_genius_find, (artist, song, f"{artist} {song}")),
        "genius-normalized":  (_genius_find, (artist, song, f"{norm_artist} {norm_song}")),
        "lrclib":             (_try_lrclib,  (artist, song)),
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures: Dict[Future, str] = {
            pool.submit(fn, *args): src
            for src, (fn, args) in _phase1.items()
        }
        for fut in as_completed(futures, timeout=12):
            src = futures[fut]
            try:
                cand = _make_candidate(fut.result(), src, artist, song)
                if cand:
                    candidates.append(cand)
                    logger.debug(
                        f"[arabic] candidate [{src}]: "
                        f"{cand['artist']!r} - {cand['song']!r} score={cand['score']:.1f}"
                    )
            except Exception as e:
                logger.debug(f"[arabic] phase-1 future [{src}] error: {e}")

    if candidates:
        best = max(candidates, key=lambda c: c["score"])
        if best["score"] >= 40:
            logger.info(
                f"[arabic] winner (phase-1): {best['artist']!r} - {best['song']!r} "
                f"score={best['score']:.1f} src={best['source']}"
            )
            return best["artist"], best["song"], best["lyrics"]

    # ── Phase 2: Romanized fallback (Layer 4) ────────────────────────────────
    if rom_artist and rom_song and _has_arabic(artist):
        logger.debug(f"[arabic] phase-2 romanized: {rom_artist!r} - {rom_song!r}")
        r4 = _genius_find(artist, song, f"{rom_artist} {rom_song}")
        if not r4:
            r4 = _try_lrclib(rom_artist, rom_song)
        cand = _make_candidate(r4, "romanized", artist, song)
        if cand:
            candidates.append(cand)

    if not candidates:
        logger.info(f"[arabic] no candidates found for {artist!r} - {song!r}")
        return None, None, None

    best = max(candidates, key=lambda c: c["score"])
    logger.info(
        f"[arabic] winner (phase-2): {best['artist']!r} - {best['song']!r} "
        f"score={best['score']:.1f} src={best['source']}"
    )
    return best["artist"], best["song"], best["lyrics"]
