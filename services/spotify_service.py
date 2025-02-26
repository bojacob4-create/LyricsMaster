import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

def get_spotify_client():
    """Initialize Spotify client."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Spotify credentials")
            return None

        logger.info("Initializing Spotify client with credentials...")

        # Create client with most basic configuration
        client_credentials = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )

        return spotipy.Spotify(client_credentials_manager=client_credentials)

    except Exception as e:
        logger.error(f"Error initializing Spotify client: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get popular tracks from Spotify."""
    try:
        spotify = get_spotify_client()
        if not spotify:
            logger.error("Failed to initialize Spotify client")
            return []

        logger.info("Starting basic search query...")

        # Use the most basic search possible
        results = spotify.search(
            q='a',  # Most basic query possible
            type='track',
            limit=limit,
            market='US'
        )

        logger.info("Search completed successfully")

        if not results:
            logger.error("Search returned empty results")
            return []

        if 'tracks' not in results:
            logger.error("No tracks field in response")
            return []

        tracks = []
        for item in results['tracks']['items']:
            try:
                name = item.get('name')
                artists = item.get('artists', [])

                if not name or not artists:
                    continue

                artist_name = artists[0].get('name', 'Unknown Artist')

                tracks.append({
                    'name': name,
                    'artist': artist_name
                })

            except Exception as e:
                logger.error(f"Error processing track: {str(e)}")
                continue

        if tracks:
            logger.info(f"Successfully processed {len(tracks)} tracks")
            return tracks[:limit]

        logger.warning("No valid tracks found in results")
        return []

    except Exception as e:
        logger.error(f"Error in get_top_tracks: {str(e)}")
        return []