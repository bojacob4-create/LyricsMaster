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


def _normalize_tokens(text: str) -> set:
    """Return a set of clean lowercase tokens, stripping punctuation and splitting hyphens."""
    text = text.lower()
    text = text.replace('-', ' ')       # split hyphenated words: "Anti-Hero" → "anti hero"
    text = _PUNCT_RE.sub('', text)      # strip non-word chars: "LOVE." → "love", "don't" → "dont"
    return set(text.split())


def _track_relevance(query_lower: str, artist: str, track: str) -> int:
    query_words  = _normalize_tokens(query_lower)
    track_words  = _normalize_tokens(track)
    artist_words = _normalize_tokens(artist)
    track_overlap  = len(track_words  & query_words)
    artist_overlap = len(artist_words & query_words)
    return artist_overlap * 10 + track_overlap * 20


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
                logger.info(f"lrclib direct hit: '{api_artist} - {api_track}'")
                return api_artist, api_track, _clean_lyrics(lyrics)
    except Exception as e:
        logger.debug(f"lrclib direct failed: {e}")
    return None


def _fetch_from_lrclib_search(query: str) -> Optional[Tuple[str, str, str]]:
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
                best       = None
                best_score = -1
                for item in data:
                    lyrics = item.get('plainLyrics', '')
                    if lyrics and len(lyrics) > 30:
                        found_artist = item.get('artistName', '')
                        found_track  = item.get('trackName',  '')
                        score = _track_relevance(query_lower, found_artist, found_track)
                        if score > best_score:
                            best_score = score
                            best = (found_artist, found_track, _clean_lyrics(lyrics))
                if best:
                    logger.info(
                        f"lrclib search hit: '{best[0]} - {best[1]}' "
                        f"(score={best_score}) for query '{query}'"
                    )
                    return best
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
            result = _fetch_from_lrclib_direct(search_artist, search_song)
            if result:
                # result is (api_artist, api_track, lyrics) — propagate API-correct names
                return result

        # Cap at 2 search queries
        search_queries = []
        if search_artist and search_song:
            search_queries.append(f"{search_artist} {search_song}")
        search_queries.append(search_song)

        for query in search_queries[:2]:
            result = _fetch_from_lrclib_search(query)
            if result:
                return result

        return None

    except Exception as e:
        logger.error(f"Error in search_song_info: {e}")
        return None
