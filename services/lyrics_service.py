import os
import lyricsgenius
from typing import Optional

# Initialize Genius API client
genius = lyricsgenius.Genius(os.getenv("GENIUS_API_KEY", ""))
genius.verbose = False
genius.remove_section_headers = True

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
        song_info = genius.search_song(song, artist)
        if song_info:
            return song_info.lyrics
        return None
    except Exception as e:
        print(f"Error fetching lyrics: {e}")
        return None