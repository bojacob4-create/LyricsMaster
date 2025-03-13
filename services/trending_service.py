import os
import logging
from typing import Dict, List
import pylast

logger = logging.getLogger(__name__)

# Initialize Last.fm API
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY")
network = pylast.LastFMNetwork(api_key=LASTFM_API_KEY)

def get_trending_tracks(limit: int = 10) -> List[Dict[str, str]]:
    """Get trending tracks from Last.fm charts."""
    try:
        # Get top tracks chart
        chart = network.get_top_tracks(limit=limit)
        
        trending_tracks = []
        for track in chart:
            track_data = {
                'artist': track.item.artist.name,
                'title': track.item.title,
                'listeners': track.weight
            }
            trending_tracks.append(track_data)
            
        return trending_tracks
    except Exception as e:
        logger.error(f"Error fetching trending tracks: {str(e)}")
        return []

def format_trending_response(tracks: List[Dict[str, str]]) -> str:
    """Format trending tracks into a readable message."""
    if not tracks:
        return "😕 Sorry, I couldn't fetch trending tracks right now.\nPlease try again later!"
    
    response = "🎵 *Top Trending Tracks Right Now* 🔥\n\n"
    for i, track in enumerate(tracks, 1):
        response += (
            f"{i}. *{track['title']}*\n"
            f"   👤 {track['artist']}\n"
            f"   👥 {track['listeners']:,} listeners\n\n"
        )
    
    response += "\nData provided by Last.fm 📊"
    return response
