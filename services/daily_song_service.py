import os
import json
import random
import logging
import requests
from typing import Dict, Optional, Tuple, List
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
    # Atomic write (tmp + rename) under a per-file lock — a crash mid-write
    # used to corrupt subscribers.json and wipe the whole subscriber list.
    try:
        from utils import atomic_json_write
        atomic_json_write(SUBSCRIBERS_FILE,
                          {str(k): v for k, v in data.items()},
                          indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving subscribers: {e}")

subscribed_users = _load_subscribers()

def _fetch_apple_music_top100() -> List[Dict]:
    """Fetch Apple Music Top 100 songs (US chart)."""
    try:
        url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'LyricsMasterBot/1.0'})
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('feed', {}).get('results', [])
            songs = []
            for item in results:
                name = item.get('name', '').strip()
                artist = item.get('artistName', '').strip()
                if name and artist:
                    songs.append({"artist": artist, "song": name})
            logger.info(f"Fetched {len(songs)} songs from Apple Music Top 100")
            return songs
    except Exception as e:
        logger.error(f"Failed to fetch Apple Music Top 100: {e}")
    return []

# Fallback static list used when Apple Music API is unavailable
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
    """Get a random song from Apple Music Top 100, falling back to static list."""
    try:
        pool = _fetch_apple_music_top100()
        if not pool:
            logger.warning("Apple Music Top 100 unavailable, using static fallback list")
            pool = DAILY_SONGS

        random.shuffle(pool)
        for song_choice in pool[:10]:
            lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])
            if not lyrics:
                logger.debug(f"No lyrics for daily candidate: {song_choice}")
                continue
            mood = detect_song_mood(lyrics)
            stats = get_song_statistics(lyrics)
            logger.info(f"Daily song selected: {song_choice['artist']} - {song_choice['song']}")
            return song_choice, lyrics, {"mood": mood, "stats": stats}

        logger.error("All daily song candidates failed to return lyrics")
        return None, None, None

    except Exception as e:
        logger.error(f"Error getting daily song: {str(e)}")
        return None, None, None


def get_daily_songs(count: int) -> List[Tuple[Dict, str, Dict]]:
    """Get *count* distinct daily songs, each verified to have lyrics."""
    results: List[Tuple[Dict, str, Dict]] = []
    seen: set = set()
    try:
        pool = _fetch_apple_music_top100()
        if not pool:
            pool = list(DAILY_SONGS)

        random.shuffle(pool)
        for song_choice in pool:
            if len(results) >= count:
                break
            key = (song_choice["artist"].lower(), song_choice["song"].lower())
            if key in seen:
                continue
            lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])
            if not lyrics:
                continue
            seen.add(key)
            mood = detect_song_mood(lyrics)
            stats = get_song_statistics(lyrics)
            results.append((song_choice, lyrics, {"mood": mood, "stats": stats}))

    except Exception as e:
        logger.error(f"Error getting daily songs: {e}")

    return results

def subscribe_user(user_id: int, chat_id: int, daily_count: int = 1) -> bool:
    """Subscribe a user to daily songs."""
    try:
        daily_count = max(1, min(3, daily_count))
        subscribed_users[user_id] = {
            "chat_id": chat_id,
            "subscribed_at": str(datetime.now()),
            "active": True,
            "daily_count": daily_count,
        }
        _save_subscribers(subscribed_users)
        logger.info(f"User {user_id} subscribed to daily songs (count={daily_count})")
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

def get_subscriber_data(user_id: int) -> Optional[Dict]:
    """Return raw subscriber data for a user, or None if not found."""
    return subscribed_users.get(user_id)

def format_daily_song(song: Dict, lyrics: str, analysis: Dict) -> str:
    """Format daily song message matching the /song command style."""
    mood_emoji = {
        'happy': '😊',
        'sad': '😢',
        'romantic': '💖',
        'energetic': '⚡',
        'relaxed': '😌'
    }.get(analysis["mood"], '🎵')

    stats = analysis["stats"]
    display_title = f"{song['artist']} - {song['song']}"

    lyrics_lines = [l.strip() for l in lyrics.strip().split('\n') if l.strip()]
    preview_lines = lyrics_lines[:4]
    lyrics_preview = '\n'.join(f"  {l}" for l in preview_lines)
    if len(lyrics_lines) > 4:
        lyrics_preview += "\n  ..."

    vocab_pct = stats.get('vocabulary_richness', 0)
    if vocab_pct >= 70:
        vocab_label = "Rich"
    elif vocab_pct >= 50:
        vocab_label = "Moderate"
    else:
        vocab_label = "Repetitive"

    return (
        "🎵 Daily Discovery\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎵 {display_title}\n\n"
        f"📝 Lyrics Preview:\n{lyrics_preview}\n\n"
        f"📊 Quick Stats:\n"
        f"  {mood_emoji} Mood: {analysis['mood'].title()}\n"
        f"  📝 Words: {stats['total_words']} | Lines: {stats['total_lines']}\n"
        f"  🧠 Vocabulary: {vocab_pct}% ({vocab_label})\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎤 /lyrics {display_title}\n"
        f"🔍 /analyze {display_title}"
    )

def send_daily_song(context) -> None:
    """Send daily song(s) to all subscribed users.

    Delivery depends on the user's chosen daily_count:
      count == 1  →  Full song dashboard text + action buttons (Lyrics / Analyze
                      / Video / MP3 / Similar).  Same quality as /song.
      count >= 2  →  Compact "Daily Picks" list with one inline button per song.
                      Tapping a button fires the full Song Dashboard (callback
                      action='song') exactly as the /song command would.
    """
    from buttons import daily_song_buttons, daily_picker_buttons

    try:
        logger.info("Starting daily song distribution")
        active = get_subscribed_users()
        logger.info(f"Sending daily songs to {len(active)} users")

        for user_id, data in active.items():
            daily_count = int(data.get("daily_count", 1))
            chat_id = data["chat_id"]

            try:
                if daily_count == 1:
                    # ── Single song: full dashboard ──────────────────────────
                    song, lyrics, analysis = get_daily_song()
                    if not all([song, lyrics, analysis]):
                        logger.error(f"Could not fetch daily song for user {user_id}")
                        continue
                    message = format_daily_song(song, lyrics, analysis)
                    btn_query = f"{song['artist']} - {song['song']}"
                    context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=None,
                        reply_markup=daily_song_buttons(btn_query),
                    )
                    logger.info(f"Sent 1 daily song to user {user_id}: {btn_query}")

                else:
                    # ── Multi-song: compact picker list ──────────────────────
                    songs_data = get_daily_songs(daily_count)
                    if not songs_data:
                        logger.error(f"Could not fetch daily songs for user {user_id}")
                        continue
                    songs = [sd[0] for sd in songs_data]
                    lines = "\n".join(
                        f"• {s['artist']} — {s['song']}" for s in songs
                    )
                    message = (
                        f"🎵 Daily Picks:\n\n"
                        f"{lines}\n\n"
                        f"Tap a song to see its full details:"
                    )
                    context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=None,
                        reply_markup=daily_picker_buttons(songs),
                    )
                    names = ", ".join(f"{s['artist']} - {s['song']}" for s in songs)
                    logger.info(f"Sent {len(songs)} daily songs to user {user_id}: {names}")

            except Exception as e:
                logger.error(f"Failed to send daily song to user {user_id}: {e}")

    except Exception as e:
        logger.error(f"Error in daily song distribution: {e}", exc_info=True)