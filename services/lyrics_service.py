import os
import logging
import time
import re
import requests
from typing import Optional
from urllib.parse import quote
from functools import lru_cache
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
session.mount('http://', adapter)
session.mount('https://', adapter)


def _fetch_from_lyrics_ovh(artist: str, song: str) -> Optional[str]:
    try:
        url = f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(song, safe='')}"
        logger.debug(f"lyrics.ovh trying: {url}")
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics')
            if lyrics:
                lyrics = lyrics.replace('\r', '')
                lyrics = '\n'.join(line.strip() for line in lyrics.split('\n'))
                return lyrics
    except Exception as e:
        logger.debug(f"lyrics.ovh failed: {e}")
    return None


def _fetch_from_lyricsgenius(artist: str, song: str) -> Optional[str]:
    try:
        api_key = os.environ.get('GENIUS_API_KEY')
        if not api_key:
            logger.debug("No GENIUS_API_KEY, skipping lyricsgenius")
            return None

        import lyricsgenius
        genius = lyricsgenius.Genius(api_key, timeout=15, retries=2, verbose=False)
        genius.remove_section_headers = True

        result = genius.search_song(song, artist)
        if result and result.lyrics:
            lyrics = result.lyrics
            lyrics = re.sub(r'\d*Embed$', '', lyrics)
            lyrics = re.sub(r'^.*Lyrics\n', '', lyrics, count=1)
            lyrics = lyrics.strip()
            if lyrics:
                return lyrics
    except Exception as e:
        logger.debug(f"lyricsgenius failed: {e}")
    return None


def _fetch_from_genius_scrape(artist: str, song: str) -> Optional[str]:
    try:
        api_key = os.environ.get('GENIUS_API_KEY')
        if not api_key:
            logger.debug("No GENIUS_API_KEY for Genius scrape")
            return None

        search_query = f"{artist} {song}".strip()
        headers = {'Authorization': f'Bearer {api_key}'}
        search_resp = session.get(
            'https://api.genius.com/search',
            params={'q': search_query},
            headers=headers,
            timeout=10
        )

        if search_resp.status_code != 200:
            return None

        data = search_resp.json()
        hits = data.get('response', {}).get('hits', [])
        if not hits:
            return None

        song_url = hits[0]['result']['url']
        logger.debug(f"Genius song URL: {song_url}")

        page_resp = session.get(song_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LyricsMasterBot/1.0)'
        })
        if page_resp.status_code != 200:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_resp.text, 'html.parser')

        lyrics_divs = soup.select('div[data-lyrics-container="true"]')
        if not lyrics_divs:
            lyrics_divs = soup.select('div[class*="Lyrics__Container"]')

        if not lyrics_divs:
            return None

        lyrics_parts = []
        for div in lyrics_divs:
            for br in div.find_all('br'):
                br.replace_with('\n')
            text = div.get_text('\n')
            lyrics_parts.append(text)

        lyrics = '\n'.join(lyrics_parts)
        lyrics = re.sub(r'\[.*?\]', '', lyrics)
        lyrics = '\n'.join(line.strip() for line in lyrics.split('\n'))
        lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
        lyrics = lyrics.strip()

        if len(lyrics) > 50:
            return lyrics

    except Exception as e:
        logger.debug(f"Genius scrape failed: {e}")
    return None


def _fetch_from_lyrist(artist: str, song: str) -> Optional[str]:
    try:
        url = f"https://lyrist.vercel.app/api/{quote(song, safe='')}/{quote(artist, safe='')}"
        logger.debug(f"lyrist trying: {url}")
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            lyrics = data.get('lyrics')
            if lyrics and len(lyrics) > 50:
                return lyrics
    except Exception as e:
        logger.debug(f"lyrist failed: {e}")
    return None


@lru_cache(maxsize=200)
def get_song_lyrics(artist: str, song: str) -> Optional[str]:
    try:
        artist = artist.strip().replace("\u2019", "'").replace('"', '')
        song = song.strip().replace("\u2019", "'").replace('"', '')

        if not artist and not song:
            return None

        search_artist = artist
        search_song = song

        if not search_song:
            search_song = search_artist
            search_artist = ''

        logger.info(f"Searching lyrics: artist='{search_artist}', song='{search_song}'")

        providers = [
            ("lyrics.ovh", _fetch_from_lyrics_ovh),
            ("genius_scrape", _fetch_from_genius_scrape),
            ("lyricsgenius", _fetch_from_lyricsgenius),
            ("lyrist", _fetch_from_lyrist),
        ]

        for name, provider in providers:
            if search_artist and search_song:
                logger.debug(f"Trying {name} with artist='{search_artist}', song='{search_song}'")
                result = provider(search_artist, search_song)
                if result:
                    logger.info(f"Found lyrics via {name}: artist='{search_artist}', song='{search_song}'")
                    return result

            if search_song:
                logger.debug(f"Trying {name} with song only: '{search_song}'")
                result = provider('', search_song)
                if result:
                    logger.info(f"Found lyrics via {name} (song-only): '{search_song}'")
                    return result

        logger.info(f"No lyrics found for: artist='{search_artist}', song='{search_song}'")
        return None

    except Exception as e:
        logger.error(f"Error fetching lyrics: {e}")
        return None
