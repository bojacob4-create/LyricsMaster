import logging
from typing import List, Dict, Optional
from datetime import datetime
from app import app, db
from models import Favorite

logger = logging.getLogger(__name__)

def add_favorite(user_id: int, artist: str, song: str) -> bool:
    """Add a song to user's favorites."""
    try:
        with app.app_context():
            # Check if song already exists for this user
            existing = Favorite.query.filter_by(
                user_id=user_id,
                artist=artist.lower(),
                song=song.lower()
            ).first()

            if existing:
                return False

            # Add new favorite
            new_favorite = Favorite(
                user_id=user_id,
                artist=artist.strip(),
                song=song.strip(),
                added_at=datetime.utcnow()
            )
            db.session.add(new_favorite)
            db.session.commit()

            logger.info(f"Added favorite for user {user_id}: {artist} - {song}")
            return True

    except Exception as e:
        logger.error(f"Error adding favorite for user {user_id}: {str(e)}")
        with app.app_context():
            db.session.rollback()
        return False

def remove_favorite(user_id: int, artist: str, song: str) -> bool:
    """Remove a song from user's favorites."""
    try:
        with app.app_context():
            favorite = Favorite.query.filter_by(
                user_id=user_id,
                artist=artist.lower(),
                song=song.lower()
            ).first()

            if not favorite:
                return False

            db.session.delete(favorite)
            db.session.commit()

            logger.info(f"Removed favorite for user {user_id}: {artist} - {song}")
            return True

    except Exception as e:
        logger.error(f"Error removing favorite for user {user_id}: {str(e)}")
        with app.app_context():
            db.session.rollback()
        return False

def get_favorites(user_id: int) -> List[Dict]:
    """Get all favorites for a user."""
    try:
        with app.app_context():
            favorites = Favorite.query.filter_by(user_id=user_id).all()
            return [favorite.to_dict() for favorite in favorites]

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