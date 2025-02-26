import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

def get_spotify_client():
    """Initialize Spotify client with retries."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Spotify credentials")
            return None

        logger.info("Initializing Spotify client...")
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        logger.error(f"Failed to initialize Spotify client: {str(e)}")
        return None

# Initialize Spotify client
spotify = get_spotify_client()

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """
    Get the current top tracks from Spotify.

    Args:
        limit (int): Number of tracks to fetch (default: 10)

    Returns:
        List[Dict]: List of track information
    """
    try:
        if not spotify:
            logger.error("Spotify client not initialized")
            return []

        logger.info("Fetching top tracks from Spotify...")

        try:
            # Try Global Top 50 first
            playlist_id = "37i9dQZEVXbMDoHDwVN2tF"
            results = spotify.playlist_tracks(
                playlist_id,
                limit=limit,
                fields="items(track(name,artists(name)))"
            )
        except Exception as e:
            logger.warning(f"Failed to fetch Global Top 50, trying Top Hits: {str(e)}")
            # Fallback to Today's Top Hits
            playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
            results = spotify.playlist_tracks(
                playlist_id,
                limit=limit,
                fields="items(track(name,artists(name)))"
            )

        tracks = []
        for item in results['items']:
            if item and 'track' in item and item['track']:
                track = item['track']
                if track and 'name' in track and 'artists' in track:
                    tracks.append({
                        'name': track['name'],
                        'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown Artist'
                    })

        logger.info(f"Successfully fetched {len(tracks)} tracks")
        return tracks
    except Exception as e:
        logger.error(f"Error fetching top tracks: {str(e)}")
        return []