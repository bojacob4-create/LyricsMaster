import os
import logging
import requests
from typing import Optional
from urllib.parse import quote
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=100)
def get_youtube_link(artist: str, song: str) -> Optional[str]:
    """
    Get YouTube video link for a song with caching.

    Args:
        artist (str): Artist name
        song (str): Song name

    Returns:
        Optional[str]: YouTube video URL or None if not found
    """
    try:
        # Format search query
        query = f"{artist} {song} official music video"
        encoded_query = quote(query)

        # Return YouTube search URL
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        return search_url

    except Exception as e:
        logger.error(f"Error getting YouTube link: {str(e)}")
        return None

def format_youtube_response(artist: str, song: str, url: str) -> str:
    """Format YouTube link response message."""
    return (
        f"🎵 {artist} - {song}\n\n"
        f"🎬 Watch on YouTube:\n{url}\n\n"
        "Note: This will take you to YouTube search results for the song."
    )