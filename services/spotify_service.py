import os
import base64
import requests
import logging
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def get_spotify_token() -> Optional[str]:
    """Get Spotify access token with retries."""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Spotify credentials")
            return None

        # Create base64 encoded string
        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')

        headers = {
            'Authorization': f'Basic {auth_base64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {'grant_type': 'client_credentials'}

        # Try up to 3 times with backoff
        for attempt in range(3):
            try:
                logger.info(f"Attempting to get token (attempt {attempt + 1}/3)")
                response = requests.post(
                    'https://accounts.spotify.com/api/token',
                    headers=headers,
                    data=data,
                    timeout=10
                )

                if response.status_code == 200:
                    token_data = response.json()
                    if 'access_token' in token_data:
                        logger.info("Successfully obtained token")
                        return token_data['access_token']
                    logger.error("Token not found in response")
                else:
                    logger.error(f"Token request failed with status {response.status_code}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {str(e)}")

            if attempt < 2:
                time.sleep(1 * (attempt + 1))  # Exponential backoff

        logger.error("Failed to get token after all retries")
        return None

    except Exception as e:
        logger.error(f"Error in get_spotify_token: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get popular tracks using Browse API."""
    try:
        token = get_spotify_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return []

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # Try to get featured playlists first
        for attempt in range(3):
            try:
                logger.info(f"Fetching featured playlists (attempt {attempt + 1}/3)")

                # Get a featured playlist first
                featured_response = requests.get(
                    'https://api.spotify.com/v1/browse/featured-playlists',
                    headers=headers,
                    params={'limit': 1, 'country': 'US'},
                    timeout=10
                )

                if featured_response.status_code != 200:
                    logger.error(f"Featured playlists request failed: {featured_response.status_code}")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                    return []

                featured_data = featured_response.json()
                if not featured_data.get('playlists', {}).get('items'):
                    logger.error("No featured playlists found")
                    return []

                # Get first playlist's tracks
                playlist_id = featured_data['playlists']['items'][0]['id']
                tracks_response = requests.get(
                    f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks',
                    headers=headers,
                    params={
                        'limit': limit,
                        'fields': 'items(track(name,artists(name)))'
                    },
                    timeout=10
                )

                if tracks_response.status_code != 200:
                    logger.error(f"Tracks request failed: {tracks_response.status_code}")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                    return []

                tracks_data = tracks_response.json()

                tracks = []
                for item in tracks_data.get('items', []):
                    try:
                        track = item.get('track', {})
                        if not track:
                            continue

                        artists = track.get('artists', [])
                        name = track.get('name')

                        if not name or not artists:
                            continue

                        artist_name = artists[0].get('name', 'Unknown Artist')
                        tracks.append({
                            'name': name,
                            'artist': artist_name
                        })
                    except Exception as e:
                        logger.warning(f"Error processing track: {str(e)}")
                        continue

                if tracks:
                    logger.info(f"Successfully fetched {len(tracks)} tracks")
                    return tracks[:limit]

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {str(e)}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue

        logger.error("Failed to get tracks after all retries")
        return []

    except Exception as e:
        logger.error(f"Error in get_top_tracks: {str(e)}")
        return []