from typing import List, Dict, Tuple
import re
from collections import Counter

def get_song_statistics(lyrics: str) -> Dict:
    """
    Analyze song lyrics and return interesting statistics.

    Args:
        lyrics (str): Song lyrics to analyze

    Returns:
        Dict: Statistics including word count, unique words, common words, etc.
    """
    stop_words = {'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 
                 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
                 'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 
                 'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
                 'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
                 'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no',
                 'just', 'him', 'know', 'take', 'into', 'your', 'some', 'could',
                 'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only',
                 'come', 'its', 'over', 'think', 'also', 'back', 'after', 'use',
                 'two', 'how', 'our', 'work', 'first', 'well', 'way', 'even',
                 'new', 'want', 'because', 'any', 'these', 'give', 'day',
                 'most', 'us', 'im', 'gonna', 'wanna', 'cause', 'yeah'}

    lyrics_clean = lyrics.lower()
    lyrics_clean = re.sub(r'\[.*?\]', '', lyrics_clean)  

    lines = [line.strip() for line in lyrics_clean.split('\n') if line.strip()]
    line_count = len(lines)

    words = re.findall(r'\b\w+\b', lyrics_clean)
    word_count = len(words)

    meaningful_words = [word for word in words if word not in stop_words]
    unique_words = set(meaningful_words)

    word_freq = Counter(meaningful_words).most_common(5)

    phrases = []
    for i in range(len(words)-2):
        phrase = ' '.join(words[i:i+3])
        phrases.append(phrase)
    repeated_phrases = [phrase for phrase, count in Counter(phrases).most_common(3) if count > 1]

    return {
        'total_lines': line_count,
        'total_words': word_count,
        'unique_words': len(unique_words),
        'top_words': word_freq,
        'repeated_phrases': repeated_phrases,
        'vocabulary_richness': round((len(unique_words) / word_count) * 100, 2)
    }

def format_statistics(stats: Dict) -> str:
    """Format song statistics into a readable message."""
    return (
        "📊 Song Statistics:\n\n"
        f"📝 Lines: {stats['total_lines']}\n"
        f"📚 Total Words: {stats['total_words']}\n"
        f"🎯 Unique Words: {stats['unique_words']}\n"
        f"🎨 Vocabulary Richness: {stats['vocabulary_richness']}%\n\n"
        "🔝 Most Used Words:\n" +
        '\n'.join(f"   • {word}: {count} times" for word, count in stats['top_words']) +
        "\n\n📎 Most Repeated Phrases:\n" +
        '\n'.join(f"   • \"{phrase}\"" for phrase in stats['repeated_phrases'][:3])
    )

def format_lyrics(lyrics: str) -> str:
    """Format lyrics for Telegram message."""
    if not lyrics:
        return "No lyrics available."

    formatted = '\n'.join(line for line in lyrics.split('\n') if line.strip())

    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."

    return formatted

def detect_song_mood(lyrics: str) -> str:
    """Detect the mood of a song based on its lyrics."""
    lyrics_lower = lyrics.lower()

    mood_keywords = {
        'happy': ['happy', 'joy', 'smile', 'laugh', 'fun', 'dance', 'party', 'sunshine'],
        'sad': ['sad', 'cry', 'tears', 'pain', 'hurt', 'alone', 'lost', 'sorry', 'missing'],
        'romantic': ['love', 'heart', 'kiss', 'beautiful', 'forever', 'darling', 'romance'],
        'energetic': ['jump', 'run', 'fire', 'burn', 'alive', 'wild', 'free', 'tonight'],
        'relaxed': ['peace', 'calm', 'quiet', 'dream', 'sleep', 'gentle', 'slow']
    }

    mood_counts = {mood: 0 for mood in mood_keywords}

    for mood, keywords in mood_keywords.items():
        for keyword in keywords:
            mood_counts[mood] += len(re.findall(r'\b' + keyword + r'\b', lyrics_lower))

    dominant_mood = max(mood_counts.items(), key=lambda x: x[1])[0]
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