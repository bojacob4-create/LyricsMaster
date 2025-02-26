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
                time.sleep(1 * (attempt + 1))

        logger.error("Failed to get token after all retries")
        return None

    except Exception as e:
        logger.error(f"Error in get_spotify_token: {str(e)}")
        return None

def get_top_tracks(limit: int = 10) -> List[Dict]:
    """Get currently popular tracks using Spotify's New Releases."""
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
                logger.debug(f"Attempt {attempt + 1} to fetch new releases")

                # Get new releases with more detailed parameters
                new_releases_response = requests.get(
                    'https://api.spotify.com/v1/browse/new-releases',
                    headers=headers,
                    params={
                        'limit': limit,
                        'country': 'US',
                        'offset': 0  # Start from the most recent
                    },
                    timeout=10
                )

                if new_releases_response.status_code == 200:
                    releases_data = new_releases_response.json()

                    if not releases_data.get('albums', {}).get('items'):
                        logger.error("No albums found in response")
                        return []

                    tracks = []
                    for album in releases_data['albums']['items']:
                        try:
                            # Get artist names
                            artist_names = [artist['name'] for artist in album['artists']]
                            artist_name = artist_names[0] if artist_names else 'Unknown Artist'

                            # Get track name (album name in this case)
                            track_name = album['name']

                            if not artist_name or not track_name:
                                logger.warning(f"Missing artist or track name for album {album.get('id')}")
                                continue

                            tracks.append({
                                'name': track_name,
                                'artist': artist_name
                            })
                            logger.debug(f"Added track: {artist_name} - {track_name}")

                        except Exception as e:
                            logger.warning(f"Error processing album: {str(e)}")
                            continue

                    if tracks:
                        logger.info(f"Successfully fetched {len(tracks)} tracks")
                        return tracks[:limit]

                    logger.warning("No valid tracks found in results")
                    return []

                elif new_releases_response.status_code == 429:  # Rate limit
                    retry_after = int(new_releases_response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue

                elif new_releases_response.status_code == 401:  # Token expired
                    logger.error("Token expired, will retry with new token")
                    token = get_spotify_token()  # Get fresh token
                    if not token:
                        return []
                    headers['Authorization'] = f'Bearer {token}'
                    continue

                else:
                    logger.error(f"New releases request failed with status {new_releases_response.status_code}")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
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