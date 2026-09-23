import re
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, List
from services.lyrics_service import search_song_info

logger = logging.getLogger(__name__)

# ── Token normalization (mirrors lyrics_service._normalize_tokens) ──────────
_PUNCT_RE = re.compile(r'[^\w\s]')


def _query_tokens(text: str) -> set:
    """Return normalized token set for relevance comparison."""
    t = text.lower().replace('-', ' ')
    t = _PUNCT_RE.sub('', t)
    return set(t.split())


def _result_score(query_tokens: set, api_artist: str, api_track: str) -> int:
    """Count how many query tokens appear in the API-returned artist + track names."""
    all_tokens = _query_tokens(api_artist) | _query_tokens(api_track)
    return len(query_tokens & all_tokens)


def _best_of(r1, r2, query: str):
    """Given two search_song_info results, return the one with better query coverage."""
    if r1 and r2:
        q = _query_tokens(query)
        s1 = _result_score(q, r1[0], r1[1])
        s2 = _result_score(q, r2[0], r2[1])
        return r1 if s1 >= s2 else r2
    return r1 or r2


def clean_input(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'["""\u201c\u201d]', '', raw)
    raw = re.sub(r"['''\u2018\u2019]", "'", raw)
    raw = re.sub(r'\s+', ' ', raw)
    return raw


def parse_song_query(raw_input: str) -> List[Tuple[str, str]]:
    logger.info(f"Parsing raw input: '{raw_input}'")
    cleaned = clean_input(raw_input)

    if not cleaned:
        logger.info("Empty input after cleaning")
        return []

    candidates = []

    if ' - ' in cleaned:
        parts = cleaned.split(' - ', 1)
        artist = parts[0].strip()
        song   = parts[1].strip()
        if artist and song:
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif ' – ' in cleaned:
        parts = cleaned.split(' – ', 1)
        artist = parts[0].strip()
        song   = parts[1].strip()
        if artist and song:
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        artist = parts[0].strip()
        song   = parts[1].strip()
        if artist and song:
            candidates.append((artist, song))
            candidates.append((song, artist))

    if not candidates:
        words = cleaned.split()
        if len(words) >= 2:
            for i in range(len(words) - 1, 0, -1):
                part1 = ' '.join(words[:i])
                part2 = ' '.join(words[i:])
                candidates.append((part1, part2))
                candidates.append((part2, part1))

    candidates.append(('', cleaned))

    seen   = set()
    unique = []
    for c in candidates:
        key = (c[0].lower(), c[1].lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)

    logger.info(f"Total unique search candidates: {len(unique)}")
    return unique


def search_lyrics_with_fallback(raw_input: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    logger.info(f"Search with fallback for: '{raw_input}'")
    cleaned = clean_input(raw_input)

    if not cleaned:
        return None, None, None, "empty_input"

    # ── Separator paths — bidirectional evaluation ────────────────────────
    # Try BOTH (left=artist, right=song) AND (left=song, right=artist),
    # then pick whichever interpretation scores better against the query.
    # This fixes "love - kendrick" where left is actually the song, not the artist.
    if ' - ' in cleaned or ' – ' in cleaned:
        sep   = ' - ' if ' - ' in cleaned else ' – '
        parts = cleaned.split(sep, 1)
        left  = parts[0].strip()
        right = parts[1].strip()

        if left and right:
            # Both orderings are independent network calls — run them in
            # parallel to halve worst-case latency on this path.
            with ThreadPoolExecutor(max_workers=2) as _pool:
                _r1 = _pool.submit(search_song_info, left,  right)  # left=artist
                _r2 = _pool.submit(search_song_info, right, left)   # right=artist
                r1, r2 = _r1.result(), _r2.result()
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Separator hit (bidirectional): '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "direct"

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        left  = parts[0].strip()
        right = parts[1].strip()

        if left and right:
            with ThreadPoolExecutor(max_workers=2) as _pool:
                _r1 = _pool.submit(search_song_info, left,  right)
                _r2 = _pool.submit(search_song_info, right, left)
                r1, r2 = _r1.result(), _r2.result()
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Compact-dash hit (bidirectional): '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "direct"

    # ── Generic search — full cleaned string ─────────────────────────────
    result = search_song_info('', cleaned)
    if result:
        found_artist, found_track, lyrics = result
        logger.info(f"Search found: '{found_artist} - {found_track}'")
        return found_artist, found_track, lyrics, "search"

    # ── Word-split fallback — capped at 3 attempts ────────────────────────
    words = cleaned.split()
    if len(words) >= 2:
        attempts = 0
        for i in range(len(words) - 1, 0, -1):
            if attempts >= 3:
                break
            part1 = ' '.join(words[:i])
            part2 = ' '.join(words[i:])
            with ThreadPoolExecutor(max_workers=2) as _pool:
                _w1 = _pool.submit(search_song_info, part1, part2)
                _w2 = _pool.submit(search_song_info, part2, part1)
                r1, r2 = _w1.result(), _w2.result()
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Word-split hit: '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "word_split"
            attempts += 1

    logger.info(f"All search attempts failed for: '{raw_input}'")
    return None, None, None, "not_found"
