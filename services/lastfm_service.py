import os
import logging
import pylast
from typing import List, Dict, Optional
import time

logger = logging.getLogger(__name__)

def get_lastfm_network() -> Optional[pylast.LastFMNetwork]:
    """Initialize Last.fm network connection with retries."""
    try:
        api_key = os.getenv("LASTFM_API_KEY")
        if not api_key:
            logger.error("Missing Last.fm API key")
            return None

        logger.info("Initializing Last.fm network with API key...")

        # Try up to 3 times with backoff
        for attempt in range(3):
            try:
                logger.debug(f"Attempt {attempt + 1} to initialize Last.fm network")
                network = pylast.LastFMNetwork(api_key=api_key)

                # Test connection with a simple geo call
                test_tracks = network.get_geo_top_tracks(country='united states', limit=1)
                if test_tracks:
                    logger.info("Successfully initialized Last.fm network")
                    return network

            except Exception as e:
                logger.error(f"Network initialization failed (attempt {attempt + 1}): {str(e)}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                continue

        logger.error("Failed to initialize Last.fm network after all retries")
        return None

    except Exception as e:
        logger.error(f"Error initializing Last.fm network: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get top tracks from Last.fm."""
    try:
        network = get_lastfm_network()
        if not network:
            logger.error("Failed to get Last.fm network")
            return []

        logger.info("Fetching top tracks from Last.fm...")

        # Get global top tracks with retries
        for attempt in range(3):
            try:
                logger.debug(f"Attempt {attempt + 1} to fetch top tracks")
                # Use geo top tracks for more reliable results
                top_tracks = network.get_geo_top_tracks(
                    country='united states',
                    limit=limit
                )

                tracks = []
                for track in top_tracks:
                    try:
                        if not track or not track.item:
                            continue

                        artist_name = track.item.get_artist().get_name()
                        track_name = track.item.get_name()

                        if not artist_name or not track_name:
                            continue

                        tracks.append({
                            'name': track_name,
                            'artist': artist_name
                        })
                        logger.debug(f"Added track: {artist_name} - {track_name}")
                    except Exception as track_error:
                        logger.warning(f"Error processing track: {str(track_error)}")
                        continue

                if tracks:
                    logger.info(f"Successfully fetched {len(tracks)} tracks")
                    return tracks[:limit]

                logger.warning("No tracks found in results")
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