import os
import lyricsgenius
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)

# Initialize Genius API client
def initialize_genius():
    try:
        genius_token = os.getenv("GENIUS_API_KEY")
        if not genius_token:
            logger.error("No Genius API key provided")
            return None

        genius = lyricsgenius.Genius(genius_token)
        genius.verbose = False
        genius.remove_section_headers = True
        # Test the connection
        genius.search_song("Test", "Test")
        return genius
    except Exception as e:
        logger.error(f"Failed to initialize Genius client: {e}")
        return None

# Initialize with retry
retries = 3
genius = None
for i in range(retries):
    genius = initialize_genius()
    if genius:
        break
    if i < retries - 1:
        time.sleep(1)  # Wait before retrying

def get_song_lyrics(artist: str, song: str) -> Optional[str]:
    """
    Get lyrics for a specific song by artist.

    Args:
        artist (str): The artist name
        song (str): The song title

    Returns:
        Optional[str]: The lyrics if found, None otherwise
    """
    try:
        if not genius:
            logger.error("Genius client not initialized")
            return None

        logger.info(f"Searching for lyrics: {artist} - {song}")

        # Clean up the search terms
        artist = artist.strip()
        song = song.strip()

        try:
            song_info = genius.search_song(song, artist)
            if song_info:
                return song_info.lyrics
        except Exception as search_error:
            logger.error(f"Error searching for song: {search_error}")
            # Try with just the song title as fallback
            try:
                song_info = genius.search_song(song)
                if song_info and any(a.name.lower() == artist.lower() for a in song_info.artist_names):
                    return song_info.lyrics
            except Exception as fallback_error:
                logger.error(f"Fallback search failed: {fallback_error}")

        logger.info(f"No lyrics found for: {artist} - {song}")
        return None
    except Exception as e:
        logger.error(f"Error fetching lyrics: {e}")
        return None