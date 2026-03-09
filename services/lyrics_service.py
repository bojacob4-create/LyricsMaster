import os
import logging
import time
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
    total=3,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
session.mount('http://', adapter)
session.mount('https://', adapter)


def _fetch_from_lrclib_direct(artist: str, song: str) -> Optional[str]:
    if not artist or not song:
        return None
    try:
        response = session.get(
            'https://lrclib.net/api/get',
            params={'artist_name': artist, 'track_name': song},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('plainLyrics', '')
            if lyrics and len(lyrics) > 30:
                logger.info(f"lrclib direct hit: artist='{artist}', song='{song}'")
                return _clean_lyrics(lyrics)
    except Exception as e:
        logger.debug(f"lrclib direct failed: {e}")
    return None


def _fetch_from_lrclib_search(query: str) -> Optional[Tuple[str, str, str]]:
    try:
        response = session.get(
            'https://lrclib.net/api/search',
            params={'q': query},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    lyrics = item.get('plainLyrics', '')
                    if lyrics and len(lyrics) > 30:
                        found_artist = item.get('artistName', '')
                        found_track = item.get('trackName', '')
                        logger.info(f"lrclib search hit: '{found_artist} - {found_track}' for query '{query}'")
                        return found_artist, found_track, _clean_lyrics(lyrics)
    except Exception as e:
        logger.debug(f"lrclib search failed: {e}")
    return None


def _fetch_from_lyrics_ovh(artist: str, song: str) -> Optional[str]:
    if not artist or not song:
        return None
    try:
        url = f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(song, safe='')}"
        response = session.get(url, timeout=8)
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
    try:
        artist = artist.strip().replace('\u2019', "'").replace('"', '').replace('\u201c', '').replace('\u201d', '')
        song = song.strip().replace('\u2019', "'").replace('"', '').replace('\u201c', '').replace('\u201d', '')

        if not artist and not song:
            return None

        search_artist = artist
        search_song = song

        if not search_song:
            search_song = search_artist
            search_artist = ''

        logger.info(f"Lyrics lookup: artist='{search_artist}', song='{search_song}'")

        if search_artist and search_song:
            result = _fetch_from_lrclib_direct(search_artist, search_song)
            if result:
                return result

            result = _fetch_from_lrclib_direct(search_song, search_artist)
            if result:
                return result

        search_queries = []
        if search_artist and search_song:
            search_queries.append(f"{search_artist} {search_song}")
            search_queries.append(f"{search_song} {search_artist}")
            search_queries.append(search_song)
        else:
            search_queries.append(search_song)

        for query in search_queries:
            result = _fetch_from_lrclib_search(query)
            if result:
                return result[2]

        if search_artist and search_song:
            result = _fetch_from_lyrics_ovh(search_artist, search_song)
            if result:
                return result

            result = _fetch_from_lyrics_ovh(search_song, search_artist)
            if result:
                return result

        logger.info(f"All providers failed for: artist='{search_artist}', song='{search_song}'")
        return None

    except Exception as e:
        logger.error(f"Error in get_song_lyrics: {e}")
        return None


def search_song_info(artist: str, song: str) -> Optional[Tuple[str, str, str]]:
    try:
        artist = artist.strip()
        song = song.strip()

        if not artist and not song:
            return None

        search_artist = artist
        search_song = song if song else artist

        if search_artist and search_song:
            result = _fetch_from_lrclib_direct(search_artist, search_song)
            if result:
                return search_artist, search_song, result

        search_queries = []
        if search_artist and search_song:
            search_queries.append(f"{search_artist} {search_song}")
        search_queries.append(search_song)

        for query in search_queries:
            result = _fetch_from_lrclib_search(query)
            if result:
                return result

        return None

    except Exception as e:
        logger.error(f"Error in search_song_info: {e}")
        return None
