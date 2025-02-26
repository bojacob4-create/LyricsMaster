import os
import logging
import requests
from typing import List, Dict, Optional
import random

logger = logging.getLogger(__name__)

def get_similar_songs(artist: str, song: str, mood: str) -> List[Dict]:
    """
    Get song recommendations based on artist, song, and mood.

    Args:
        artist (str): Artist name
        song (str): Song name
        mood (str): Detected mood of the song

    Returns:
        List[Dict]: List of recommended songs with their artists
    """
    try:
        # First try to get recommendations from Spotify
        spotify_token = os.getenv("SPOTIFY_CLIENT_SECRET")
        if spotify_token:
            recommendations = _get_spotify_recommendations(artist, song)
            if recommendations:
                return recommendations

        # Fallback to mood-based recommendations
        return _get_mood_based_recommendations(mood)

    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return []

def _get_spotify_recommendations(artist: str, song: str) -> Optional[List[Dict]]:
    """Get recommendations using Spotify's API."""
    try:
        # Get Spotify token
        token = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not token:
            return None

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # Search for the track to get its ID
        search_url = 'https://api.spotify.com/v1/search'
        search_params = {
            'q': f'track:{song} artist:{artist}',
            'type': 'track',
            'limit': 1
        }
        
        search_response = requests.get(search_url, headers=headers, params=search_params)
        if search_response.status_code != 200:
            return None

        search_data = search_response.json()
        if not search_data.get('tracks', {}).get('items'):
            return None

        track_id = search_data['tracks']['items'][0]['id']

        # Get recommendations based on the track
        rec_url = 'https://api.spotify.com/v1/recommendations'
        rec_params = {
            'seed_tracks': track_id,
            'limit': 5
        }

        rec_response = requests.get(rec_url, headers=headers, params=rec_params)
        if rec_response.status_code != 200:
            return None

        rec_data = rec_response.json()
        recommendations = []
        
        for track in rec_data.get('tracks', []):
            recommendations.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown Artist'
            })

        return recommendations

    except Exception as e:
        logger.error(f"Error getting Spotify recommendations: {str(e)}")
        return None

def _get_mood_based_recommendations(mood: str) -> List[Dict]:
    """Get recommendations based on song mood."""
    # Predefined mood-based song recommendations
    mood_songs = {
        'happy': [
            {'artist': 'Pharrell Williams', 'name': 'Happy'},
            {'artist': 'Justin Timberlake', 'name': "Can't Stop the Feeling"},
            {'artist': 'Katy Perry', 'name': 'Firework'},
            {'artist': 'Mark Ronson', 'name': 'Uptown Funk'},
            {'artist': 'Walk the Moon', 'name': 'Shut Up and Dance'}
        ],
        'sad': [
            {'artist': 'Adele', 'name': 'Someone Like You'},
            {'artist': 'Sam Smith', 'name': 'Stay With Me'},
            {'artist': 'Lewis Capaldi', 'name': 'Someone You Loved'},
            {'artist': 'James Arthur', 'name': 'Say You Won\'t Let Go'},
            {'artist': 'Christina Perri', 'name': 'A Thousand Years'}
        ],
        'romantic': [
            {'artist': 'Ed Sheeran', 'name': 'Perfect'},
            {'artist': 'John Legend', 'name': 'All of Me'},
            {'artist': 'Elvis Presley', 'name': "Can't Help Falling in Love"},
            {'artist': 'Bruno Mars', 'name': 'Just the Way You Are'},
            {'artist': 'Jason Mraz', 'name': "I'm Yours"}
        ],
        'energetic': [
            {'artist': 'Survivor', 'name': 'Eye of the Tiger'},
            {'artist': 'Queen', 'name': 'We Will Rock You'},
            {'artist': 'Eminem', 'name': 'Lose Yourself'},
            {'artist': 'AC/DC', 'name': 'Thunderstruck'},
            {'artist': 'The White Stripes', 'name': 'Seven Nation Army'}
        ],
        'relaxed': [
            {'artist': 'Jack Johnson', 'name': 'Better Together'},
            {'artist': 'Israel Kamakawiwo\'ole', 'name': 'Somewhere Over the Rainbow'},
            {'artist': 'Bob Marley', 'name': 'Three Little Birds'},
            {'artist': 'Jason Mraz', 'name': 'Lucky'},
            {'artist': 'Coldplay', 'name': 'Fix You'}
        ]
    }

    # Get songs for the given mood, or energetic as default
    mood_matches = mood_songs.get(mood, mood_songs['energetic'])
    
    # Randomly select 3 songs to recommend
    return random.sample(mood_matches, min(3, len(mood_matches)))

def format_recommendations(recommendations: List[Dict], based_on: str = None) -> str:
    """Format recommendations into a readable message."""
    if not recommendations:
        return "😅 Sorry, I couldn't find any recommendations right now."

    message = "🎵 Here are some songs you might like:\n\n"
    if based_on:
        message = f"🎵 Based on the mood of \"{based_on}\", you might like:\n\n"

    for i, song in enumerate(recommendations, 1):
        message += f"{i}. {song['artist']} - {song['name']}\n"

    message += "\nTry /lyrics with any of these songs to check them out! 🎧"
    return message
