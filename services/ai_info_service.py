import logging
import re
from typing import Optional, Dict
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cached dictionary of known artists for faster lookups
KNOWN_ARTISTS = {
    'taylor': {'name': 'Taylor Swift', 'gender': 'f', 'genre': 'pop', 'style': 'pop crossover'},
    'adele': {'name': 'Adele', 'gender': 'f', 'genre': 'pop', 'style': 'soul-pop'},
    'beyonce': {'name': 'Beyoncé', 'gender': 'f', 'genre': 'r&b', 'style': 'r&b/pop'},
    'lady': {'name': 'Lady Gaga', 'gender': 'f', 'genre': 'pop', 'style': 'dance-pop'},
    'ariana': {'name': 'Ariana Grande', 'gender': 'f', 'genre': 'pop', 'style': 'pop/r&b'},
    'justin': {'name': 'Justin Bieber', 'gender': 'm', 'genre': 'pop', 'style': 'pop/r&b'},
    'ed': {'name': 'Ed Sheeran', 'gender': 'm', 'genre': 'pop', 'style': 'pop/folk'},
    'drake': {'name': 'Drake', 'gender': 'm', 'genre': 'hip-hop', 'style': 'rap/r&b'},
    'weeknd': {'name': 'The Weeknd', 'gender': 'm', 'genre': 'r&b', 'style': 'alternative r&b'},
    'eminem': {'name': 'Eminem', 'gender': 'm', 'genre': 'hip-hop', 'style': 'rap'},
    'bruno': {'name': 'Bruno Mars', 'gender': 'm', 'genre': 'pop', 'style': 'funk/pop'},
    'rihanna': {'name': 'Rihanna', 'gender': 'f', 'genre': 'pop', 'style': 'pop/r&b'},
    'dua': {'name': 'Dua Lipa', 'gender': 'f', 'genre': 'pop', 'style': 'dance-pop'},
    'post': {'name': 'Post Malone', 'gender': 'm', 'genre': 'hip-hop', 'style': 'rap/pop'},
    'kendrick': {'name': 'Kendrick Lamar', 'gender': 'm', 'genre': 'hip-hop', 'style': 'conscious rap'}
}

# Cached genre achievements for faster response generation
GENRE_ACHIEVEMENTS = {
    'pop': "• Multiple platinum records and chart-topping singles\n• Successful worldwide tours and performances\n• Influential presence in mainstream music",
    'hip-hop': "• Critically acclaimed albums and mixtapes\n• Groundbreaking collaborations and features\n• Influential contributions to hip-hop culture",
    'r&b': "• Soulful performances and vocal excellence\n• Genre-defining musical productions\n• Emotional storytelling through music"
}

@lru_cache(maxsize=100)
def get_person_info(name: str) -> Optional[Dict[str, str]]:
    """
    Generate a personalized artist information response.

    Args:
        name (str): Name of the person to search for

    Returns:
        Optional[Dict[str, str]]: Dictionary containing title and information if found
    """
    try:
        # Clean up the name
        name = name.strip()
        if not name:
            return None

        # Get artist info using cached data
        first_name = name.split()[0].lower()
        artist_info = KNOWN_ARTISTS.get(first_name, {'gender': 'n', 'genre': 'music', 'style': 'contemporary'})

        # Get pronouns based on gender
        pronoun = 'she' if artist_info['gender'] == 'f' else 'he' if artist_info['gender'] == 'm' else 'they'
        possessive = 'her' if artist_info['gender'] == 'f' else 'his' if artist_info['gender'] == 'm' else 'their'

        # Get achievements from cached data
        achievements = GENRE_ACHIEVEMENTS.get(artist_info['genre'], 
            "• Notable releases and performances\n• Strong artistic vision and execution\n• Dedicated following in the music industry")

        # Generate response using pre-formatted strings
        info = (
            f"🎵 Career Overview:\n"
            f"{name} has made an extraordinary impact in {artist_info['genre']} music with {possessive} distinctive "
            f"{artist_info['style']} style. As a leading voice in contemporary music, {pronoun} continues to inspire "
            f"audiences worldwide through powerful performances and innovative artistry.\n\n"

            f"🎸 Musical Style & Expression:\n"
            f"• Known for {possessive} unique {artist_info['style']} sound and artistic vision\n"
            f"• Creates music that pushes boundaries and sets new trends\n"
            f"• Masterful at connecting with audiences through authentic expression\n\n"

            f"🏆 Achievements & Impact:\n"
            f"{achievements}\n\n"

            f"💫 Artistic Legacy:\n"
            f"• {name} continues to evolve and innovate in the {artist_info['genre']} scene\n"
            f"• Influences new generations of artists with {possessive} distinctive approach\n"
            f"• Sets new standards for excellence in modern music"
        )

        return {
            "title": name,
            "info": info
        }

    except Exception as e:
        logger.error(f"Error generating info: {str(e)}")
        return None