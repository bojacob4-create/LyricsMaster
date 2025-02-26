import os
import logging
import time
import requests
from typing import Optional
from urllib.parse import quote
from functools import lru_cache

logger = logging.getLogger(__name__)

# Configure session with retries and connection pooling
session = requests.Session()
retries = requests.packages.urllib3.util.retry.Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
)
session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))

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
        artist = artist.strip().replace("'", "'").replace('"', '')
        song = song.strip().replace("'", "'").replace('"', '')

        logger.debug(f"Attempting to fetch lyrics for: {artist} - {song}")

        # Try multiple endpoint variations
        endpoints = [
            f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(song, safe='')}",
            f"https://api.lyrics.ovh/v1/{quote(artist.lower(), safe='')}/{quote(song.lower(), safe='')}",
            # Add alternative endpoint for special characters
            f"https://api.lyrics.ovh/v1/{quote(''.join(c for c in artist if c.isalnum() or c.isspace()), safe='')}/{quote(''.join(c for c in song if c.isalnum() or c.isspace()), safe='')}"
        ]

        for endpoint in endpoints:
            try:
                logger.debug(f"Trying endpoint: {endpoint}")
                response = session.get(endpoint, timeout=10)

                logger.debug(f"Response status code: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    lyrics = data.get('lyrics')

                    if lyrics:
                        logger.debug("Successfully retrieved lyrics")
                        # Clean up lyrics formatting
                        lyrics = lyrics.replace('\r', '')
                        lyrics = '\n'.join(line.strip() for line in lyrics.split('\n'))
                        return lyrics

                    logger.debug("Empty lyrics in response")
                    continue

                elif response.status_code == 404:
                    logger.debug("Lyrics not found at this endpoint")
                    continue

                elif response.status_code == 429:
                    logger.debug("Rate limit hit, waiting before retry")
                    time.sleep(2)  # Longer wait for rate limits
                    continue

                elif response.status_code >= 500:
                    logger.debug(f"Server error {response.status_code}, trying next endpoint")
                    continue

            except requests.exceptions.Timeout:
                logger.debug(f"Timeout for endpoint: {endpoint}")
                continue
            except requests.exceptions.RequestException as e:
                logger.debug(f"Request failed for endpoint: {endpoint}, error: {str(e)}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error for endpoint: {endpoint}, error: {str(e)}")
                continue

        # Final attempt with basic alphanumeric characters
        logger.debug("All endpoints failed, trying one last time with simplified terms")
        artist_simple = ''.join(c for c in artist if c.isalnum() or c.isspace()).strip()
        song_simple = ''.join(c for c in song if c.isalnum() or c.isspace()).strip()

        if artist_simple != artist or song_simple != song:
            logger.debug(f"Attempting with simplified terms: {artist_simple} - {song_simple}")
            return get_song_lyrics(artist_simple, song_simple)

        logger.info(f"No lyrics found after trying all variations for: {artist} - {song}")
        return None

    except Exception as e:
        logger.error(f"Error fetching lyrics: {str(e)}")
        return None