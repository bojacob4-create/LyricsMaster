import os
import json
import random
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from services.lyrics_service import get_song_lyrics
from utils import detect_song_mood, get_song_statistics

logger = logging.getLogger(__name__)

SUBSCRIBERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'subscribers.json')

def _load_subscribers() -> Dict:
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, 'r') as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Error loading subscribers: {e}")
    return {}

def _save_subscribers(data: Dict) -> None:
    try:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            json.dump({str(k): v for k, v in data.items()}, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving subscribers: {e}")

subscribed_users = _load_subscribers()

# List of curated songs for daily recommendations
DAILY_SONGS = [
    {"artist": "The Beatles", "song": "Hey Jude"},
    {"artist": "Queen", "song": "Bohemian Rhapsody"},
    {"artist": "Michael Jackson", "song": "Billie Jean"},
    {"artist": "Whitney Houston", "song": "I Will Always Love You"},
    {"artist": "Ed Sheeran", "song": "Perfect"},
    {"artist": "Adele", "song": "Someone Like You"},
    {"artist": "Taylor Swift", "song": "Shake It Off"},
    {"artist": "Elvis Presley", "song": "Can't Help Falling in Love"},
    {"artist": "Bob Marley", "song": "Three Little Birds"},
    {"artist": "John Lennon", "song": "Imagine"},
    {"artist": "Tyla", "song": "Water"},
    {"artist": "Dua Lipa", "song": "Levitating"},
    {"artist": "Harry Styles", "song": "As It Was"},
    {"artist": "The Weeknd", "song": "Blinding Lights"},
    {"artist": "Billie Eilish", "song": "bad guy"},
    {"artist": "Bruno Mars", "song": "Just the Way You Are"},
    {"artist": "Rihanna", "song": "Umbrella"},
    {"artist": "Coldplay", "song": "Yellow"},
    {"artist": "Imagine Dragons", "song": "Believer"},
    {"artist": "SZA", "song": "Kill Bill"},
    {"artist": "Fleetwood Mac", "song": "Dreams"},
    {"artist": "Hozier", "song": "Take Me to Church"},
    {"artist": "Olivia Rodrigo", "song": "drivers license"},
    {"artist": "Post Malone", "song": "Circles"},
    {"artist": "Ariana Grande", "song": "thank u, next"},
    {"artist": "Miley Cyrus", "song": "Flowers"},
    {"artist": "Lewis Capaldi", "song": "Someone You Loved"},
    {"artist": "Beyonce", "song": "Halo"},
    {"artist": "Lana Del Rey", "song": "Summertime Sadness"},
    {"artist": "Arctic Monkeys", "song": "Do I Wanna Know?"},
]

def get_daily_song() -> Tuple[Dict, str, Dict]:
    """Get a random song with its lyrics and analysis."""
    try:
        # Pick a random song
        song_choice = random.choice(DAILY_SONGS)

        # Get lyrics
        lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])
        if not lyrics:
            logger.error(f"Could not fetch lyrics for daily song: {song_choice}")
            return None, None, None

        # Analyze song
        mood = detect_song_mood(lyrics)
        stats = get_song_statistics(lyrics)

        return song_choice, lyrics, {
            "mood": mood,
            "stats": stats
        }

    except Exception as e:
        logger.error(f"Error getting daily song: {str(e)}")
        return None, None, None

def subscribe_user(user_id: int, chat_id: int) -> bool:
    """Subscribe a user to daily songs."""
    try:
        subscribed_users[user_id] = {
            "chat_id": chat_id,
            "subscribed_at": str(datetime.now()),
            "active": True
        }
        _save_subscribers(subscribed_users)
        logger.info(f"User {user_id} subscribed to daily songs")
        return True
    except Exception as e:
        logger.error(f"Error subscribing user {user_id}: {str(e)}")
        return False

def unsubscribe_user(user_id: int) -> bool:
    """Unsubscribe a user from daily songs."""
    try:
        if user_id in subscribed_users:
            subscribed_users[user_id]["active"] = False
            _save_subscribers(subscribed_users)
            logger.info(f"User {user_id} unsubscribed from daily songs")
        return True
    except Exception as e:
        logger.error(f"Error unsubscribing user {user_id}: {str(e)}")
        return False

def get_subscribed_users() -> Dict:
    """Get all actively subscribed users."""
    return {uid: data for uid, data in subscribed_users.items() 
            if data.get("active", False)}

def format_daily_song(song: Dict, lyrics: str, analysis: Dict) -> str:
    """Format daily song message."""
    mood_emoji = {
        'happy': '😊',
        'sad': '😢',
        'romantic': '💖',
        'energetic': '⚡',
        'relaxed': '😌'
    }.get(analysis["mood"], '🎵')

    stats = analysis["stats"]

    return (
        "🎵 Daily Song Discovery\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Today's Pick: {song['artist']} — {song['song']}\n\n"
        f"Mood: {mood_emoji} {analysis['mood'].title()}\n"
        f"📝 {stats['total_lines']} lines  •  {stats['total_words']} words\n"
        f"🎨 Vocabulary: {stats['vocabulary_richness']}%\n\n"
        "── Preview ──\n\n"
        f"{lyrics[:800]}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎤 /lyrics {song['artist']} - {song['song']}\n"
        f"📊 /analyze {song['artist']} - {song['song']}\n"
        f"🎵 /recommend {song['artist']} - {song['song']}"
    )

def send_daily_song(context) -> None:
    """Send daily song to all subscribed users."""
    try:
        logger.info("Starting daily song distribution")

        song, lyrics, analysis = get_daily_song()
        if not all([song, lyrics, analysis]):
            logger.error("Failed to get daily song")
            return

        message = format_daily_song(song, lyrics, analysis)

        # Send to all subscribed users
        subscribed_users = get_subscribed_users()
        logger.info(f"Sending daily song to {len(subscribed_users)} users")

        for user_id, data in subscribed_users.items():
            try:
                context.bot.send_message(
                    chat_id=data["chat_id"],
                    text=message,
                    parse_mode=None  # Ensure no parsing issues
                )
                logger.info(f"Sent daily song to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send daily song to user {user_id}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in daily song distribution: {str(e)}", exc_info=True)