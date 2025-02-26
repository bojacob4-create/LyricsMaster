import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict
import logging
import time

logger = logging.getLogger(__name__)

def get_spotify_client():
    """Initialize Spotify client with retries."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.error("Missing Spotify credentials")
        return None

    logger.info("Initializing Spotify client...")
    logger.debug(f"Using client ID: {client_id[:5]}...")  # Log first 5 chars for debugging

    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        spotify = spotipy.Spotify(
            auth_manager=auth_manager,
            requests_timeout=10,
            retries=3
        )

        # Test the client with a simple search
        logger.info("Testing Spotify client connection...")
        test_result = spotify.search(q='test', type='track', limit=1)
        if test_result and test_result['tracks']['items']:
            logger.info("Spotify client initialized and tested successfully")
            return spotify
        else:
            logger.error("Spotify client test failed - no results returned")
            return None

    except Exception as e:
        logger.error(f"Failed to initialize Spotify client: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """
    Get the current top tracks from Spotify.

    Args:
        limit (int): Number of tracks to fetch (default: 10)

    Returns:
        List[Dict]: List of track information
    """
    try:
        logger.info("Starting get_top_tracks function")
        spotify = get_spotify_client()  # Get a fresh client for each request

        if not spotify:
            logger.error("Could not initialize Spotify client")
            return []

        logger.info("Fetching top tracks from Spotify...")

        # Try both playlists in sequence
        playlists = [
            ("Today's Top Hits", "37i9dQZF1DXcBWIGoYBM5M"),
            ("Global Top 50", "37i9dQZEVXbMDoHDwVN2tF")
        ]

        for playlist_name, playlist_id in playlists:
            try:
                logger.info(f"Attempting to fetch from {playlist_name} playlist...")
                results = spotify.playlist_tracks(
                    playlist_id,
                    limit=limit,
                    fields="items(track(name,artists(name)))"
                )

                tracks = []
                for item in results['items']:
                    if not item or 'track' not in item:
                        continue

                    track = item['track']
                    if not track or 'name' not in track or 'artists' not in track:
                        continue

                    artist_name = track['artists'][0]['name'] if track['artists'] else "Unknown Artist"
                    tracks.append({
                        'name': track['name'],
                        'artist': artist_name
                    })

                if tracks:
                    logger.info(f"Successfully fetched {len(tracks)} tracks from {playlist_name}")
                    return tracks

                logger.warning(f"No valid tracks found in {playlist_name} playlist")

            except Exception as e:
                logger.error(f"Error fetching tracks from {playlist_name}: {str(e)}")
                continue

        logger.error("Failed to fetch tracks from all playlists")
        return []

    except Exception as e:
        logger.error(f"Error in get_top_tracks: {str(e)}")
        return []