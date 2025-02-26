import os
import logging
import pylast
from typing import List, Dict, Optional
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cache the network connection
_lastfm_network = None

def get_lastfm_network() -> Optional[pylast.LastFMNetwork]:
    """Initialize Last.fm network connection with caching."""
    global _lastfm_network

    try:
        # Return cached network if available
        if _lastfm_network is not None:
            return _lastfm_network

        api_key = os.getenv("LASTFM_API_KEY")
        if not api_key:
            logger.error("Missing Last.fm API key")
            return None

        # Try up to 3 times with backoff
        for attempt in range(3):
            try:
                network = pylast.LastFMNetwork(api_key=api_key)

                # Test connection with a lightweight call
                network.get_user("test").get_name()

                # Cache and return the network
                _lastfm_network = network
                return network

            except pylast.WSError as ws_error:
                logger.error(f"Last.fm Web Service error: {ws_error}")
                return None
            except Exception as e:
                logger.error(f"Network initialization failed (attempt {attempt + 1}): {str(e)}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                continue

        logger.error("Failed to initialize Last.fm network after all retries")
        return None

    except Exception as e:
        logger.error(f"Error initializing Last.fm network: {str(e)}")
        return None

@lru_cache(maxsize=50, timeout=300)  # Cache results for 5 minutes
def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get top tracks from Last.fm metro area with caching."""
    try:
        network = get_lastfm_network()
        if not network:
            logger.error("Failed to get Last.fm network")
            return []

        # Try up to 3 times with backoff
        for attempt in range(3):
            try:
                # Get metro tracks for New York
                metro_tracks = network.get_metro_tracks(
                    metro="New York",
                    country="United States",
                    limit=limit
                )

                tracks = []
                for track in metro_tracks:
                    try:
                        if not track or not isinstance(track, pylast.Track):
                            continue

                        artist_name = str(track.artist)
                        track_name = str(track.title)

                        if not artist_name or not track_name:
                            continue

                        tracks.append({
                            'name': track_name,
                            'artist': artist_name
                        })

                    except Exception as track_error:
                        logger.warning(f"Error processing track: {str(track_error)}")
                        continue

                if tracks:
                    return tracks[:limit]

                logger.warning("No tracks found in results")
                return []

            except pylast.WSError as ws_error:
                logger.error(f"Last.fm Web Service error: {ws_error}")
                return []
            except Exception as e:
                logger.error(f"Failed to fetch tracks (attempt {attempt + 1}): {str(e)}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue

        logger.error("Failed to get tracks after all retries")
        return []

    except Exception as e:
        logger.error(f"Error fetching top tracks: {str(e)}")
        return []