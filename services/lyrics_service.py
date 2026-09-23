import os
import logging
import re
import requests
from typing import Optional, Tuple
from urllib.parse import quote
from functools import lru_cache
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

session = requests.Session()
retries = Retry(
    total=1,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
session.mount('http://', adapter)
session.mount('https://', adapter)

# ── Token normalization ────────────────────────────────────────────────────
# Used by _track_relevance to ensure "LOVE." == "love", "Anti-Hero" == "anti hero"
_PUNCT_RE = re.compile(r'[^\w\s]')

# Words that indicate a track is NOT the canonical original release.
# Applied to track name only (never to artist name).
# Conservative list — only unambiguous non-original markers.
_COVER_WORDS = frozenset({
    'cover', 'karaoke', 'tribute', 'parody', 'bootleg', 'mashup', 'vip', 'remix',
})

# ── Video-suffix stripping (round 5) ──────────────────────────────────────
# Providers sometimes return track names like
# "Rod Wave - Dope Girl (Official Audio)". These suffixes are display noise —
# strip them so the user always sees a clean "Artist - Song".
_VIDEO_SUFFIX_RES = [
    re.compile(r'\s*[\(\[]\s*official\s+(?:music\s+)?video\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*official\s+audio\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*official\s+lyric(?:s)?\s+video\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*music\s+video\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*lyric\s+video\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*lyrics\s+video\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*visualizer\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*[\(\[]\s*audio\s*[\)\]]\s*$', re.IGNORECASE),
    re.compile(r'\s*-\s*official\s+(?:music\s+)?video\s*$', re.IGNORECASE),
    re.compile(r'\s*-\s*official\s+audio\s*$', re.IGNORECASE),
]


def canonicalize_track_names(artist: str, track: str) -> Tuple[str, str]:
    """Return a clean (artist, track) pair for display.

    - Dedupes a repeated artist name embedded in the track
      ("Rod Wave - Dope Girl" with artist "Rod Wave" → "Dope Girl").
    - Strips video suffixes ("(Official Audio)", "[Official Video]").
    - Normalizes whitespace.
    Parentheticals that are part of the real title
    ("(from GTAVI: The Album)") are left untouched.
    """
    artist = re.sub(r'\s+', ' ', (artist or '')).strip()
    track = re.sub(r'\s+', ' ', (track or '')).strip()
    if artist and track:
        lowered = track.lower()
        a_lower = artist.lower()
        stripped = False
        for sep in (' - ', ' – ', ' — ', '-'):
            if lowered.startswith(a_lower + sep):
                rest = track[len(artist) + len(sep):].strip()
                if len(rest) >= 2:
                    track = rest
                    stripped = True
                break
        if not stripped and lowered.startswith(a_lower + ' '):
            rest = track[len(artist) + 1:].strip()
            if len(rest) >= 2:
                track = rest
        for rx in _VIDEO_SUFFIX_RES:
            new = rx.sub('', track).strip()
            if new and new != track:
                track = new
        track = re.sub(r'\s+', ' ', track).strip()
    return artist, track


def _normalize_tokens(text: str) -> set:
    """Return a set of clean lowercase tokens, stripping punctuation and splitting hyphens."""
    text = text.lower()
    text = text.replace('-', ' ')       # split hyphenated words: "Anti-Hero" → "anti hero"
    text = _PUNCT_RE.sub('', text)      # strip non-word chars: "LOVE." → "love", "don't" → "dont"
    return set(text.split())


def _is_non_original(track: str) -> bool:
    """Return True when the track name clearly flags a non-original (cover/remix/VIP/etc.)."""
    tl = track.lower()
    return any(cw in tl for cw in _COVER_WORDS)


def _track_relevance(query_lower: str, artist: str, track: str) -> int:
    query_words  = _normalize_tokens(query_lower)
    track_words  = _normalize_tokens(track)
    artist_words = _normalize_tokens(artist)
    track_overlap  = len(track_words  & query_words)
    artist_overlap = len(artist_words & query_words)
    return artist_overlap * 10 + track_overlap * 20


def _clean_slug_title(slug: str, artist: str) -> str:
    """Convert a URL slug like 'Artist-Name-Song-Title-' into 'Song Title'.

    Only fires when *slug* has no spaces (all-hyphen format) and ≥ 3 hyphens.
    Strips the artist-name prefix when it appears at the start of the un-slugged string.
    """
    if ' ' in slug or slug.count('-') < 3:
        return slug
    unslug = slug.replace('-', ' ').strip()
    if artist:
        artist_lower = artist.lower().replace('-', ' ').strip()
        unslug_lower = unslug.lower()
        if unslug_lower.startswith(artist_lower):
            remainder = unslug[len(artist):].strip()
            if remainder:
                unslug = remainder
    return unslug.title() if unslug else slug


def _fetch_from_lrclib_direct(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    """Returns (api_artist, api_track, lyrics) using names from the API response, or None."""
    if not artist or not song:
        return None
    try:
        response = session.get(
            'https://lrclib.net/api/get',
            params={'artist_name': artist, 'track_name': song},
            timeout=3
        )
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('plainLyrics', '')
            if lyrics and len(lyrics) > 30:
                api_artist = data.get('artistName', artist)
                api_track  = data.get('trackName',  song)
                api_artist, api_track = canonicalize_track_names(api_artist, api_track)
                logger.info(f"lrclib direct hit: '{api_artist} - {api_track}'")
                return api_artist, api_track, _clean_lyrics(lyrics)
    except Exception as e:
        logger.debug(f"lrclib direct failed: {e}")
    return None


def _fetch_from_lrclib_search(
    query: str,
    expected_artist: str = '',
) -> Optional[Tuple[str, str, str]]:
    """Search lrclib and return the best-matching (artist, track, lyrics) tuple.

    Two-pass preference:
      1. Prefer clean originals (tracks without cover/remix/VIP markers).
      2. Fall back to non-originals only when no clean result exists.

    When *expected_artist* is provided (non-empty), results whose artist matches
    gain a +25 bonus; those that don't match get a −25 penalty.  This prevents
    "Hood Gone Love It (Jay Rock)" from outscoring "LOVE. (Kendrick Lamar)"
    when the user explicitly typed the artist name.
    """
    try:
        response = session.get(
            'https://lrclib.net/api/search',
            params={'q': query},
            timeout=3
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                query_lower = query.lower()
                ea_toks = _normalize_tokens(expected_artist) if expected_artist else set()

                best_clean       = None
                best_clean_score = -1
                best_any         = None
                best_any_score   = -1

                for item in data:
                    lyrics = item.get('plainLyrics', '')
                    if not lyrics or len(lyrics) <= 30:
                        continue
                    found_artist = item.get('artistName', '')
                    found_track  = item.get('trackName',  '')
                    score = _track_relevance(query_lower, found_artist, found_track)

                    if ea_toks:
                        fa_toks = _normalize_tokens(found_artist)
                        if ea_toks & fa_toks:
                            score += 25
                        else:
                            score -= 25

                    entry = (found_artist, found_track, _clean_lyrics(lyrics))

                    if score > best_any_score:
                        best_any_score = score
                        best_any = entry

                    if not _is_non_original(found_track) and score > best_clean_score:
                        best_clean_score = score
                        best_clean = entry

                result = best_clean if best_clean is not None else best_any
                if result:
                    ra, rt, rl = result
                    ra, rt = canonicalize_track_names(ra, rt)
                    result = (ra, rt, rl)
                    logger.info(
                        f"lrclib search hit: '{ra} - {rt}' "
                        f"(score={best_clean_score if best_clean else best_any_score},"
                        f" clean={'yes' if best_clean else 'no'}) for query '{query}'"
                    )
                return result
    except Exception as e:
        logger.debug(f"lrclib search failed: {e}")
    return None


def _fetch_from_lyrics_ovh(artist: str, song: str) -> Optional[str]:
    if not artist or not song:
        return None
    try:
        url = f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(song, safe='')}"
        response = session.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics')
            if lyrics and len(lyrics) > 30:
                logger.info(f"lyrics.ovh hit: artist='{artist}', song='{song}'")
                return _clean_lyrics(lyrics)
    except Exception as e:
        logger.debug(f"lyrics.ovh failed: {e}")
    return None


def _clean_lyrics(lyrics: str) -> str:
    lyrics = lyrics.replace('\r', '')
    lines = []
    for line in lyrics.split('\n'):
        cleaned = line.strip()
        cleaned = re.sub(r'^\[\d{2}:\d{2}\.\d{2}\]\s*', '', cleaned)
        lines.append(cleaned)
    result = '\n'.join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


@lru_cache(maxsize=200)
def get_song_lyrics(artist: str, song: str) -> Optional[str]:
    """Fetch lyrics text only. Returns None on failure. Callers that need corrected
    artist/track names should use search_song_info instead."""
    try:
        artist = artist.strip().replace('\u2019', "'").replace('"', '').replace('\u201c', '').replace('\u201d', '')
        song   = song.strip().replace('\u2019', "'").replace('"', '').replace('\u201c', '').replace('\u201d', '')

        if not artist and not song:
            return None

        search_artist = artist
        search_song   = song

        if not search_song:
            search_song   = search_artist
            search_artist = ''

        logger.info(f"Lyrics lookup: artist='{search_artist}', song='{search_song}'")

        if search_artist and search_song:
            result = _fetch_from_lrclib_direct(search_artist, search_song)
            if result:
                return result[2]

            result = _fetch_from_lrclib_direct(search_song, search_artist)
            if result:
                return result[2]

        # Cap at 2 search queries to avoid excessive API calls
        search_queries = []
        if search_artist and search_song:
            search_queries.append(f"{search_artist} {search_song}")
            search_queries.append(f"{search_song} {search_artist}")
        else:
            search_queries.append(search_song)

        for query in search_queries[:2]:
            result = _fetch_from_lrclib_search(query)
            if result:
                return result[2]

        if search_artist and search_song:
            result = _fetch_from_lyrics_ovh(search_artist, search_song)
            if result:
                return result

        logger.info(f"All providers failed for: artist='{search_artist}', song='{search_song}'")
        return None

    except Exception as e:
        logger.error(f"Error in get_song_lyrics: {e}")
        return None


@lru_cache(maxsize=200)
def search_song_info(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    """Search for a song and return (api_artist, api_track, lyrics) using the
    API-corrected names, or None. Results are cached by (artist, song) key."""
    try:
        artist = artist.strip()
        song   = song.strip()

        if not artist and not song:
            return None

        search_artist = artist
        search_song   = song if song else artist

        if search_artist and search_song:
            # Try direct lookup — primary ordering
            result = _fetch_from_lrclib_direct(search_artist, search_song)
            if result:
                return result
            # Try swapped ordering (handles "Song - Artist" inputs)
            result = _fetch_from_lrclib_direct(search_song, search_artist)
            if result:
                return result

        # Cap at 2 search queries via lrclib search API.
        # Pass search_artist as expected_artist so the scorer can reward
        # results whose artist matches the explicitly-named artist in the query
        # and penalise results from unrelated artists.
        search_queries = []
        if search_artist and search_song:
            search_queries.append(f"{search_artist} {search_song}")
        search_queries.append(search_song)

        for query in search_queries[:2]:
            result = _fetch_from_lrclib_search(query, expected_artist=search_artist)
            if result:
                return result

        # Last-resort: lyrics.ovh (returns lyrics only — use passed-in names).
        # Clean slug-style song names (e.g. "Billie-Eilish-Happier-Than-Ever-")
        # that the user may have copy-pasted from a URL before displaying them.
        if search_artist and search_song:
            ovh_lyrics = _fetch_from_lyrics_ovh(search_artist, search_song)
            if ovh_lyrics:
                clean_song = _clean_slug_title(search_song, search_artist)
                search_artist, clean_song = canonicalize_track_names(search_artist, clean_song)
                logger.info(
                    f"lyrics.ovh fallback hit in search_song_info: "
                    f"'{search_artist} - {clean_song}'"
                )
                return search_artist, clean_song, ovh_lyrics

        return None

    except Exception as e:
        logger.error(f"Error in search_song_info: {e}")
        return None
