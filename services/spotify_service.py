import os
import base64
import requests
import logging
import time
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from functools import lru_cache

logger = logging.getLogger(__name__)

# Configure session with retries and connection pooling
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
)
session.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10))

@lru_cache(maxsize=100, timeout=3600)  # Cache token for 1 hour
def get_spotify_token() -> Optional[str]:
    """Get Spotify access token with caching."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Spotify credentials")
            return None

        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')

        url = 'https://accounts.spotify.com/api/token'
        headers = {
            'Authorization': f'Basic {auth_base64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {'grant_type': 'client_credentials'}

        response = session.post(url, headers=headers, data=data, timeout=5)

        if response.status_code == 200:
            token_data = response.json()
            if 'access_token' in token_data:
                return token_data['access_token']
            logger.error("Token not found in response")
        else:
            logger.error(f"Failed to get token: {response.status_code}")

        return None

    except requests.exceptions.Timeout:
        logger.error("Timeout getting Spotify token")
        return None
    except Exception as e:
        logger.error(f"Error getting token: {str(e)}")
        return None

@lru_cache(maxsize=50, timeout=300)  # Cache results for 5 minutes
def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get currently trending tracks from Spotify Charts with caching."""
    try:
        token = get_spotify_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return []

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # Get top tracks from Spotify's Featured Playlists
        playlists_response = session.get(
            'https://api.spotify.com/v1/browse/featured-playlists',
            headers=headers,
            params={
                'country': 'US',
                'limit': 1,
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
            },
            timeout=5
        )

        if playlists_response.status_code != 200:
            logger.error(f"Featured playlists request failed: {playlists_response.status_code}")
            return []

        playlists_data = playlists_response.json()
        if not playlists_data.get('playlists', {}).get('items'):
            logger.error("No featured playlists found")
            return []

        # Get tracks from the first featured playlist
        playlist_id = playlists_data['playlists']['items'][0]['id']
        tracks_response = session.get(
            f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks',
            headers=headers,
            params={
                'limit': limit,
                'fields': 'items(track(name,artists(name)))'
            },
            timeout=5
        )

        if tracks_response.status_code != 200:
            logger.error(f"Tracks request failed: {tracks_response.status_code}")
            return []

        tracks_data = tracks_response.json()
        if 'items' not in tracks_data:
            logger.error("Invalid response structure")
            return []

        tracks = []
        for item in tracks_data['items']:
            try:
                track = item.get('track', {})
                if not track:
                    continue

                artist_names = [artist['name'] for artist in track.get('artists', [])]
                track_name = track.get('name')

                if not track_name or not artist_names:
                    continue

                tracks.append({
                    'name': track_name,
                    'artist': artist_names[0]
                })

            except Exception as e:
                logger.warning(f"Error processing track: {str(e)}")
                continue

        return tracks[:limit]

    except requests.exceptions.Timeout:
        logger.error("Timeout getting Spotify tracks")
        return []
    except Exception as e:
        logger.error(f"Error in get_top_tracks: {str(e)}")
        return []