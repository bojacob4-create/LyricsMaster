import os
import logging
import time
import requests
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

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
        artist = artist.strip()
        song = song.strip()

        logger.info(f"Searching for lyrics: {artist} - {song}")

        # URL encode the artist and song names
        artist_encoded = quote(artist)
        song_encoded = quote(song)

        # Lyrics.ovh API endpoint
        url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{song_encoded}"

        # Try up to 3 times
        retries = 3
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    lyrics = response.json().get('lyrics')
                    if lyrics:
                        logger.info("Successfully found lyrics")
                        return lyrics
                    logger.warning("Empty lyrics returned from API")
                    return None

                elif response.status_code == 404:
                    logger.info(f"No lyrics found for: {artist} - {song}")
                    return None

                else:
                    logger.warning(f"API request failed with status {response.status_code}")
                    if attempt < retries - 1:
                        time.sleep(1)  # Wait before retry
                        continue
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(1)  # Wait before retry
                    continue
                return None

        return None

    except Exception as e:
        logger.error(f"Error fetching lyrics: {str(e)}")
        return None