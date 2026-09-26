import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Tuple, List
from services.lyrics_service import search_song_info

logger = logging.getLogger(__name__)

# ── Overall search budget (round 63) ─────────────────────────────────────────
# Each lyrics source already has a per-call timeout, but the fallback chain
# (direct x2 -> search x2 -> ovh, times two orderings in parallel) stacks them
# into a 20s+ hang during a network flap (seen 2026-09-26: 22.5s for a single
# lookup). This caps the WHOLE search_lyrics_with_fallback call instead, so a
# stuck downstream fails fast and the caller can answer instead of hanging.
LYRICS_SEARCH_TIMEOUT = 15.0


def _parallel_search(pairs: List[Tuple[str, str]], deadline: float):
    """Run search_song_info over (artist, song) pairs in parallel, bounded by deadline.

    Returns a list of results (None for timed-out or failed pairs). Never raises.
    A pair still running when the deadline hits is abandoned — its thread
    finishes the fallback chain on its own; we just stop waiting for it.
    """
    if not pairs:
        return []
    pool = ThreadPoolExecutor(max_workers=len(pairs))
    try:
        futs = [pool.submit(search_song_info, a, s) for a, s in pairs]
        out = []
        for f in futs:
            try:
                out.append(f.result(timeout=max(0.0, deadline - time.time())))
            except FuturesTimeoutError:
                out.append(None)
            except Exception:
                out.append(None)
        return out
    finally:
        # Never block on stragglers.
        pool.shutdown(wait=False, cancel_futures=True)

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


def search_lyrics_with_fallback(raw_input: str, timeout: float = LYRICS_SEARCH_TIMEOUT) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    logger.info(f"Search with fallback for: '{raw_input}'")
    cleaned = clean_input(raw_input)

    if not cleaned:
        return None, None, None, "empty_input"

    # Overall budget for the whole chain (round 63): every stage below shares
    # this deadline, so a flap can't stack per-call timeouts into a 20s+ hang.
    deadline = time.time() + timeout

    def _expired() -> bool:
        return time.time() >= deadline

    # ── Separator paths ─ bidirectional evaluation ────────────────────────
    # Try BOTH (left=artist, right=song) AND (left=song, right=artist),
    # then pick whichever interpretation scores better against the query.
    # This fixes "love - kendrick" where left is actually the song, not the artist.
    if ' - ' in cleaned or ' \u2013 ' in cleaned:
        sep   = ' - ' if ' - ' in cleaned else ' \u2013 '
        parts = cleaned.split(sep, 1)
        left  = parts[0].strip()
        right = parts[1].strip()

        if left and right:
            # Both orderings are independent network calls ─ run them in
            # parallel to halve worst-case latency on this path.
            r1, r2 = _parallel_search([(left, right), (right, left)], deadline)
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Separator hit (bidirectional): '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "direct"

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        left  = parts[0].strip()
        right = parts[1].strip()

        if left and right:
            r1, r2 = _parallel_search([(left, right), (right, left)], deadline)
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Compact-dash hit (bidirectional): '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "direct"

    # ── Generic search ─ full cleaned string ────────────────────────────
    if not _expired():
        (result,) = _parallel_search([('', cleaned)], deadline)
        if result:
            found_artist, found_track, lyrics = result
            logger.info(f"Search found: '{found_artist} - {found_track}'")
            return found_artist, found_track, lyrics, "search"

    # ── Word-split fallback ─ capped at 3 attempts ───────────────────
    words = cleaned.split()
    if len(words) >= 2:
        attempts = 0
        for i in range(len(words) - 1, 0, -1):
            if attempts >= 3 or _expired():
                break
            part1 = ' '.join(words[:i])
            part2 = ' '.join(words[i:])
            r1, r2 = _parallel_search([(part1, part2), (part2, part1)], deadline)
            best = _best_of(r1, r2, cleaned)
            if best:
                logger.info(f"Word-split hit: '{best[0]} - {best[1]}'")
                return best[0], best[1], best[2], "word_split"
            attempts += 1

    if _expired():
        logger.warning(f"Lyrics search deadline ({timeout}s) exceeded for: '{raw_input}'")
    else:
        logger.info(f"All search attempts failed for: '{raw_input}'")
    return None, None, None, "not_found"
