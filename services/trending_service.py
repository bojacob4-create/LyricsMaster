import os
import logging
from typing import Dict, List
import pylast

logger = logging.getLogger(__name__)

# Initialize Last.fm API
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY")

def get_trending_tracks(limit: int = 10) -> List[Dict[str, str]]:
    """Get trending tracks from Last.fm charts."""
    try:
        if not LASTFM_API_KEY:
            logger.error("LASTFM_API_KEY not found in environment variables")
            return []

        # Initialize network with error handling
        try:
            network = pylast.LastFMNetwork(api_key=LASTFM_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Last.fm network: {e}")
            return []

        # Get top tracks chart
        try:
            chart = network.get_top_tracks(limit=limit)

            trending_tracks = []
            for track in chart:
                try:
                    track_data = {
                        'artist': track.item.artist.name,
                        'title': track.item.title,
                        'listeners': track.weight
                    }
                    trending_tracks.append(track_data)
                except Exception as e:
                    logger.warning(f"Error processing track: {e}")
                    continue

            return trending_tracks
        except Exception as e:
            logger.error(f"Error fetching top tracks: {e}")
            return []

    except Exception as e:
        logger.error(f"Error in get_trending_tracks: {e}")
        return []

def format_trending_response(tracks: List[Dict[str, str]]) -> str:
    """Format trending tracks into a readable message."""
    if not tracks:
        return "😕 Sorry, I couldn't fetch trending tracks right now.\nPlease try again later!"

    response = "🎵 *Top Trending Tracks Right Now* 🔥\n\n"

    for i, track in enumerate(tracks, 1):
        try:
            response += (
                f"{i}. *{track['title']}*\n"
                f"   👤 {track['artist']}\n"
                f"   👥 {track['listeners']:,} listeners\n\n"
            )
        except Exception as e:
            logger.warning(f"Error formatting track {i}: {e}")
            continue

    if response == "🎵 *Top Trending Tracks Right Now* 🔥\n\n":
        return "😕 Sorry, I couldn't format the trending tracks.\nPlease try again later!"

    response += "\nData provided by Last.fm 📊"
    return response