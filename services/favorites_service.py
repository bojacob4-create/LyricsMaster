import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Store user favorites in memory (can be migrated to database later)
user_favorites = {}

def add_favorite(user_id: int, artist: str, song: str) -> bool:
    """Add a song to user's favorites."""
    try:
        if user_id not in user_favorites:
            user_favorites[user_id] = []
        
        # Check if song already exists
        for favorite in user_favorites[user_id]:
            if favorite['artist'].lower() == artist.lower() and favorite['song'].lower() == song.lower():
                return False
        
        # Add new favorite
        user_favorites[user_id].append({
            'artist': artist.strip(),
            'song': song.strip(),
            'added_at': datetime.now()
        })
        logger.info(f"Added favorite for user {user_id}: {artist} - {song}")
        return True

    except Exception as e:
        logger.error(f"Error adding favorite for user {user_id}: {str(e)}")
        return False

def remove_favorite(user_id: int, artist: str, song: str) -> bool:
    """Remove a song from user's favorites."""
    try:
        if user_id not in user_favorites:
            return False
        
        # Find and remove the song
        for favorite in user_favorites[user_id]:
            if favorite['artist'].lower() == artist.lower() and favorite['song'].lower() == song.lower():
                user_favorites[user_id].remove(favorite)
                logger.info(f"Removed favorite for user {user_id}: {artist} - {song}")
                return True
        
        return False

    except Exception as e:
        logger.error(f"Error removing favorite for user {user_id}: {str(e)}")
        return False

def get_favorites(user_id: int) -> List[Dict]:
    """Get all favorites for a user."""
    try:
        return user_favorites.get(user_id, [])

    except Exception as e:
        logger.error(f"Error getting favorites for user {user_id}: {str(e)}")
        return []

def format_favorites_list(favorites: List[Dict]) -> str:
    """Format favorites list for display."""
    if not favorites:
        return "Your favorites list is empty! ⭐\nAdd songs using /favorite artist - song"
    
    header = "⭐ Your Favorite Songs:\n\n"
    formatted_songs = [
        f"{i+1}. {favorite['artist']} - {favorite['song']}"
        for i, favorite in enumerate(favorites)
    ]
    
    footer = "\nUse /unfavorite artist - song to remove songs"
    
    return header + '\n'.join(formatted_songs) + footer
