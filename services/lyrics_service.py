import os
import logging
import time
import requests
from typing import Optional
from urllib.parse import quote
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=100)
def get_song_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Get lyrics for a specific song by artist using lyrics.ovh API.

    Args:
        artist (str): The artist name
        song (str): The song title

    Returns:
        Optional[str]: The lyrics if found, None otherwise
    """
    try:
        # Clean up search terms
        artist = artist.strip().replace("'", "'")  # Handle special apostrophes
        song = song.strip().replace("'", "'")

        logger.info(f"Searching for lyrics: {artist} - {song}")

        # URL encode the artist and song names properly
        artist_encoded = quote(artist, safe='')
        song_encoded = quote(song, safe='')

        # Lyrics.ovh API endpoint
        url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{song_encoded}"

        # Configure session with retries
        session = requests.Session()
        retries = requests.packages.urllib3.util.retry.Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))

        # Try up to 3 times
        for attempt in range(3):
            try:
                response = session.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    lyrics = data.get('lyrics')
                    if lyrics:
                        # Clean up lyrics formatting
                        lyrics = lyrics.replace('\r', '')
                        lyrics = '\n'.join(line.strip() for line in lyrics.split('\n'))
                        return lyrics
                    logger.warning("Empty lyrics returned from API")

                elif response.status_code == 404:
                    # Try with slightly modified search terms
                    if attempt == 0:
                        # Try without special characters
                        artist_clean = ''.join(c for c in artist if c.isalnum() or c.isspace())
                        song_clean = ''.join(c for c in song if c.isalnum() or c.isspace())
                        if artist_clean != artist or song_clean != song:
                            artist, song = artist_clean, song_clean
                            continue
                    logger.info(f"No lyrics found for: {artist} - {song}")
                    return None

                else:
                    logger.warning(f"API request failed with status {response.status_code}")
                    if attempt < 2:
                        time.sleep(1)  # Wait before retry
                        continue
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                if attempt < 2:
                    time.sleep(1)  # Wait before retry
                    continue
                return None

        return None

    except Exception as e:
        logger.error(f"Error fetching lyrics: {str(e)}")
        return None