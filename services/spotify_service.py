import os
import base64
import requests
import logging
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def get_spotify_token() -> Optional[str]:
    """Get Spotify access token."""
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

        logger.info("Getting Spotify access token...")
        response = requests.post(url, headers=headers, data=data, timeout=10)

        if response.status_code == 200:
            token_data = response.json()
            if 'access_token' in token_data:
                logger.info("Successfully obtained Spotify token")
                return token_data['access_token']
            logger.error("Token not found in response")
        else:
            logger.error(f"Failed to get token: {response.status_code}")
            logger.error(f"Response: {response.text}")

        return None

    except Exception as e:
        logger.error(f"Error getting token: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get currently trending tracks from Spotify Charts."""
    try:
        token = get_spotify_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return []

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        logger.info("Fetching top tracks from Spotify...")

        # Try up to 3 times with backoff
        for attempt in range(3):
            try:
                logger.debug(f"Attempt {attempt + 1} to fetch top tracks")

                # Get top tracks from Spotify's Featured Playlists
                playlists_response = requests.get(
                    'https://api.spotify.com/v1/browse/featured-playlists',
                    headers=headers,
                    params={
                        'country': 'US',
                        'limit': 1,
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
                    },
                    timeout=10
                )

                if playlists_response.status_code != 200:
                    logger.error(f"Featured playlists request failed: {playlists_response.status_code}")
                    logger.error(f"Response: {playlists_response.text}")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                    return []

                playlists_data = playlists_response.json()
                if not playlists_data.get('playlists', {}).get('items'):
                    logger.error("No featured playlists found")
                    return []

                # Get tracks from the first featured playlist
                playlist_id = playlists_data['playlists']['items'][0]['id']
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
                    logger.error(f"Response: {tracks_response.text}")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                    return []

                tracks_data = tracks_response.json()
                if 'items' not in tracks_data:
                    logger.error("Invalid response structure")
                    logger.debug(f"Response data: {tracks_data}")
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
                            logger.warning("Missing track info")
                            continue

                        tracks.append({
                            'name': track_name,
                            'artist': artist_names[0]
                        })
                        logger.debug(f"Added track: {artist_names[0]} - {track_name}")

                    except Exception as e:
                        logger.warning(f"Error processing track: {str(e)}")
                        continue

                if tracks:
                    logger.info(f"Successfully fetched {len(tracks)} tracks")
                    return tracks[:limit]

                logger.warning("No tracks found in results")
                return []

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