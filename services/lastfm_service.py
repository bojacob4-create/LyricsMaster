import os
import logging
import pylast
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def get_lastfm_network() -> Optional[pylast.LastFMNetwork]:
    """Initialize Last.fm network connection."""
    try:
        api_key = os.getenv("LASTFM_API_KEY")
        if not api_key:
            logger.error("Missing Last.fm API key")
            return None

        logger.info("Initializing Last.fm network...")
        network = pylast.LastFMNetwork(api_key=api_key)
        return network

    except Exception as e:
        logger.error(f"Error initializing Last.fm network: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get global top tracks from Last.fm."""
    try:
        network = get_lastfm_network()
        if not network:
            logger.error("Failed to initialize Last.fm network")
            return []

        logger.info("Fetching top tracks from Last.fm...")
        
        # Get global top tracks
        top_tracks = network.get_top_tracks(limit=limit)
        
        tracks = []
        for track in top_tracks:
            try:
                tracks.append({
                    'name': track.item.get_name(),
                    'artist': track.item.get_artist().get_name()
                })
            except Exception as track_error:
                logger.warning(f"Error processing track: {str(track_error)}")
                continue

        if tracks:
            logger.info(f"Successfully fetched {len(tracks)} tracks")
            return tracks

        logger.warning("No tracks found")
        return []

    except Exception as e:
        logger.error(f"Error fetching top tracks: {str(e)}")
        return []
