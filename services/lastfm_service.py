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

                # Simple connection test
                if network.get_user("rj"):  # Test with a known Last.fm user
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
    """Get top tracks from Last.fm's weekly chart."""
    try:
        network = get_lastfm_network()
        if not network:
            logger.error("Failed to get Last.fm network")
            return []

        logger.info("Fetching top tracks from Last.fm...")

        # Get weekly chart tracks with retries
        for attempt in range(3):
            try:
                logger.debug(f"Attempt {attempt + 1} to fetch top tracks")

                # Get global weekly chart
                weekly_chart = network.get_weekly_chart_tracks(limit=limit)
                if not weekly_chart:
                    logger.error("Empty weekly chart returned")
                    continue

                tracks = []
                for track in weekly_chart:
                    try:
                        if not track or not track[0]:
                            continue

                        artist_name = str(track[0].artist)
                        track_name = str(track[0].title)

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