import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict

# Initialize Spotify client
spotify = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
    )
)

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """
    Get the current top tracks from Spotify.

    Args:
        limit (int): Number of tracks to fetch (default: 10)

    Returns:
        List[Dict]: List of track information
    """
    try:
        # Get the "Global Top 50" playlist
        playlist_id = "37i9dQZEVXbMDoHDwVN2tF"
        results = spotify.playlist_tracks(
            playlist_id,
            limit=limit,
            fields="items(track(name,artists(name)))"
        )

        tracks = []
        for item in results['items']:
            track = item['track']
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name']
            })

        return tracks
    except Exception as e:
        print(f"Error fetching top tracks: {e}")
        return []