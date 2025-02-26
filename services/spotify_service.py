import os
import logging
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict

logger = logging.getLogger(__name__)

def get_spotify_client():
    """Initialize Spotify client."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Spotify credentials")
            return None

        logger.info("Initializing Spotify client...")

        # Create client credentials without cache
        credentials = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
            cache_handler=None  # Disable caching
        )

        spotify = spotipy.Spotify(
            auth_manager=credentials,
            requests_timeout=10
        )

        return spotify

    except Exception as e:
        logger.error(f"Failed to initialize Spotify client: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get current top tracks from Spotify Charts."""
    try:
        spotify = get_spotify_client()
        if not spotify:
            logger.error("Could not initialize Spotify client")
            return []

        logger.info("Fetching top tracks from Spotify...")

        # Fetch Featured Playlists (more reliable endpoint)
        playlists = spotify.featured_playlists(limit=1)
        if not playlists or 'playlists' not in playlists:
            logger.error("Could not fetch featured playlists")
            return []

        playlist_items = playlists['playlists']['items']
        if not playlist_items:
            logger.error("No featured playlists found")
            return []

        # Get tracks from the first featured playlist
        playlist_id = playlist_items[0]['id']
        results = spotify.playlist_tracks(
            playlist_id,
            limit=limit,
            fields="items(track(name,artists(name)))"
        )

        if not results or 'items' not in results:
            logger.error("Invalid response format from Spotify API")
            return []

        tracks = []
        for item in results['items']:
            try:
                track = item.get('track', {})
                if not track:
                    continue

                artists = track.get('artists', [])
                artist_name = artists[0].get('name', 'Unknown Artist') if artists else 'Unknown Artist'

                tracks.append({
                    'name': track.get('name', 'Unknown Track'),
                    'artist': artist_name
                })
            except Exception as track_error:
                logger.warning(f"Error processing track: {str(track_error)}")
                continue

        if tracks:
            logger.info(f"Successfully fetched {len(tracks)} tracks")
            return tracks[:limit]

        logger.warning("No tracks found in playlist")
        return []

    except Exception as e:
        logger.error(f"Error in get_top_tracks: {str(e)}")
        return []