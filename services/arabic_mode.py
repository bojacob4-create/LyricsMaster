"""
services/arabic_mode.py

Arabic Songs Mode — Fully Isolated Pipeline.
Self-contained subsystem. Does NOT modify or mutate any main bot logic.
All external calls are read-only (no side-effects on shared state).
"""

import re
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

# ── Arabic normalization ──────────────────────────────────────────────────────

_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670]')
_TATWEEL_RE    = re.compile(r'\u0640')
_DASH_RE       = re.compile(r'[–—\u2012\u2013\u2014\u2015]')


def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for search matching.
    Returns a cleaned copy; the original is never overwritten.
    """
    text = _DASH_RE.sub('-', text)
    text = _DIACRITICS_RE.sub('', text)
    text = _TATWEEL_RE.sub('', text)
    for ch in 'أإآٱ':
        text = text.replace(ch, 'ا')
    text = text.replace('ى', 'ي')
    text = text.replace('ؤ', 'و')
    text = text.replace('ئ', 'ي')
    text = text.replace('ء', '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Input parsing ─────────────────────────────────────────────────────────────

_FORMAT_ERROR = (
    "Please use the correct format:\n"
    "Artist - Song\n\n"
    "Example:\n"
    "ماجد المهندس - ضايع"
)


def parse_arabic_input(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Strictly parse "artist - song" format.
    Returns (artist, song, None) on success, or (None, None, error_msg) on failure.
    """
    text = _DASH_RE.sub('-', text.strip())
    if ' - ' not in text:
        return None, None, _FORMAT_ERROR
    parts = text.split(' - ', 1)
    artist = parts[0].strip()
    song   = parts[1].strip()
    if not artist or not song:
        return None, None, _FORMAT_ERROR
    return artist, song, None


# ── Hard filter ───────────────────────────────────────────────────────────────

_REJECT_WORDS = frozenset([
    'remix', 'live', 'cover', 'slowed', 'sped up', 'karaoke',
    'reverb', 'instrumental', 'acoustic', 'tribute', 'mashup',
])


def _is_non_original(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in _REJECT_WORDS)


# ── Scoring ───────────────────────────────────────────────────────────────────

def _token_set(text: str) -> set:
    norm = normalize_arabic(text)
    return set(norm.split()) | set(text.lower().split())


def _token_overlap(query: str, candidate: str) -> float:
    qt = _token_set(query)
    ct = _token_set(candidate)
    if not qt:
        return 0.0
    return len(qt & ct) / len(qt)


def _score(query_artist: str, query_song: str, cand_artist: str, cand_song: str) -> float:
    """Score 0–100: artist 50%, song 40%, clean title 10%."""
    a = _token_overlap(query_artist, cand_artist) * 50
    s = _token_overlap(query_song,   cand_song)   * 40
    c = 0 if _is_non_original(cand_song) else 10
    return a + s + c


# ── Layer helpers ─────────────────────────────────────────────────────────────

def _try_lyrics(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    """Call existing search_song_info read-only. Returns (artist, track, lyrics) or None."""
    try:
        from services.lyrics_service import search_song_info
        return search_song_info(artist, song)
    except Exception as e:
        logger.debug(f"[arabic] lyrics_service({artist!r}, {song!r}) failed: {e}")
        return None


# ── Layer 4: simple Arabic → Latin transliteration ───────────────────────────

_AR_LATIN = str.maketrans({
    'ا': 'a',  'ب': 'b',  'ت': 't',  'ث': 'th', 'ج': 'j',  'ح': 'h',
    'خ': 'kh', 'د': 'd',  'ذ': 'dh', 'ر': 'r',  'ز': 'z',  'س': 's',
    'ش': 'sh', 'ص': 's',  'ض': 'd',  'ط': 't',  'ظ': 'z',  'ع': '',
    'غ': 'gh', 'ف': 'f',  'ق': 'q',  'ك': 'k',  'ل': 'l',  'م': 'm',
    'ن': 'n',  'ه': 'h',  'و': 'w',  'ي': 'y',  'ة': 'a',  'ى': 'a',
    'أ': 'a',  'إ': 'e',  'آ': 'a',  'ء': '',
})


def _romanize(text: str) -> str:
    text = normalize_arabic(text)
    result = text.translate(_AR_LATIN)
    return re.sub(r'\s+', ' ', result).strip()


# ── Main resolver ─────────────────────────────────────────────────────────────

def resolve_arabic_song(
    artist: str,
    song:   str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Multi-layer resolver with parallel execution and early-stop.
    Returns (resolved_artist, resolved_song, lyrics) or (None, None, None).
    Never falls back into main bot logic on failure.
    """
    norm_artist = normalize_arabic(artist)
    norm_song   = normalize_arabic(song)
    candidates: List[Dict] = []

    def _add(result, src: str):
        if not result:
            return
        ra, rs, rl = result
        score = _score(artist, song, ra, rs)
        if _is_non_original(rs):
            score -= 30
        candidates.append({
            'artist': ra, 'song': rs, 'lyrics': rl,
            'score': score, 'source': src,
        })

    # Layers 1 + 2 in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_try_lyrics, artist, song)
        f2 = pool.submit(_try_lyrics, norm_artist, norm_song)
        _add(f1.result(), 'original')
        _add(f2.result(), 'normalized')

    # Early stop if strong match already found
    if candidates:
        best = max(candidates, key=lambda c: c['score'])
        if best['score'] >= 60:
            logger.info(
                f"[arabic] early stop: {best['artist']!r} - {best['song']!r} "
                f"score={best['score']:.1f} src={best['source']}"
            )
            return best['artist'], best['song'], best['lyrics']

    # Layer 3: swapped artist/song
    _add(_try_lyrics(norm_song, norm_artist), 'swapped')

    # Layer 4: romanized fallback (only if nothing yet or low confidence)
    rom_artist = _romanize(artist)
    rom_song   = _romanize(song)
    if rom_artist and rom_song and rom_artist != artist:
        _add(_try_lyrics(rom_artist, rom_song), 'romanized')

    if not candidates:
        logger.info(f"[arabic] no candidates for {artist!r} - {song!r}")
        return None, None, None

    best = max(candidates, key=lambda c: c['score'])
    logger.info(
        f"[arabic] winner: {best['artist']!r} - {best['song']!r} "
        f"score={best['score']:.1f} src={best['source']}"
    )
    return best['artist'], best['song'], best['lyrics']
