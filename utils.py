from typing import List, Dict
import re

def format_lyrics(lyrics: str) -> str:
    """
    Format lyrics for Telegram message.

    Args:
        lyrics (str): Raw lyrics text

    Returns:
        str: Formatted lyrics
    """
    if not lyrics:
        return "No lyrics available."

    # Remove extra blank lines and trim
    formatted = '\n'.join(line for line in lyrics.split('\n') if line.strip())

    # Telegram has a message length limit
    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    return formatted

def detect_song_mood(lyrics: str) -> str:
    """
    Detect the mood of a song based on its lyrics.

    Args:
        lyrics (str): Song lyrics

    Returns:
        str: Detected mood (happy, sad, romantic, energetic, or relaxed)
    """
    # Convert to lowercase for analysis
    lyrics_lower = lyrics.lower()

    # Define mood indicators
    mood_keywords = {
        'happy': ['happy', 'joy', 'smile', 'laugh', 'fun', 'dance', 'party', 'sunshine'],
        'sad': ['sad', 'cry', 'tears', 'pain', 'hurt', 'alone', 'lost', 'sorry', 'missing'],
        'romantic': ['love', 'heart', 'kiss', 'beautiful', 'forever', 'darling', 'romance'],
        'energetic': ['jump', 'run', 'fire', 'burn', 'alive', 'wild', 'free', 'tonight'],
        'relaxed': ['peace', 'calm', 'quiet', 'dream', 'sleep', 'gentle', 'slow']
    }

    # Count occurrences of mood keywords
    mood_counts = {mood: 0 for mood in mood_keywords}

    for mood, keywords in mood_keywords.items():
        for keyword in keywords:
            mood_counts[mood] += len(re.findall(r'\b' + keyword + r'\b', lyrics_lower))

    # Get the mood with highest count
    dominant_mood = max(mood_counts.items(), key=lambda x: x[1])[0]

    # Default to 'energetic' if no clear mood is detected
    return dominant_mood if mood_counts[dominant_mood] > 0 else 'energetic'

def format_top_tracks(tracks: List[Dict]) -> str:
    """
    Format top tracks for Telegram message.

    Args:
        tracks (List[Dict]): List of track information

    Returns:
        str: Formatted track list
    """
    if not tracks:
        return "❌ Sorry, couldn't fetch top tracks right now.\nPlease try again in a few minutes."

    header = "🎵 New & Trending Tracks:\n\n"
    formatted_tracks = [
        f"{i+1}. {track['artist']} - {track['name']}"
        for i, track in enumerate(tracks)
    ]

    return header + '\n'.join(formatted_tracks)