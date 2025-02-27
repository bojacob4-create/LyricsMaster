from typing import List, Dict, Tuple
import re
from collections import Counter, defaultdict

def get_song_statistics(lyrics: str) -> Dict:
    """
    Analyze song lyrics and return interesting statistics.

    Args:
        lyrics (str): Song lyrics to analyze

    Returns:
        Dict: Statistics including word count, unique words, common words, etc.
    """
    # Enhanced stop words list with common lyrics-specific words and contractions
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
                'most', 'us', 'im', 'gonna', 'wanna', 'cause', 'yeah', 'oh',
                'uh', 'huh', 'hmm', 'la', 'na', 'ooh', 'hey', 'yo', 'um',
                'chorus', 'verse', 'bridge', 'repeat', 'instrumental', 'outro',
                'intro', 'refrain', 'pre', 'ive', 've', 're', 'll', 'd', 'm', 's',
                'dont', 'cant', 'wont', 'aint', 'youre', 'youve', 'youll',
                'thats', 'wasnt', 'hadnt', 'hasnt', 'havent', 'didnt', 'isnt'}

    # First, get the line count from the original lyrics
    lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
    line_count = len(lines)

    # Then process the lyrics for word analysis
    lyrics_clean = lyrics.lower()
    # Remove section markers but preserve line breaks
    lyrics_clean = re.sub(r'\[.*?\]', '', lyrics_clean)
    # Special handling for contractions - preserve apostrophes in known contractions
    lyrics_clean = re.sub(r"'(?!(ve|re|ll|s|m|d|t)\\b)", " ", lyrics_clean)
    # Remove other punctuation except apostrophes
    lyrics_clean = re.sub(r'[^\w\s\']', ' ', lyrics_clean)
    # Replace multiple spaces with single space
    lyrics_clean = re.sub(r'\s+', ' ', lyrics_clean)

    # Get all words, keeping contractions intact
    words = re.findall(r"\b[a-z']+\b", lyrics_clean)
    word_count = len(words)

    # Filter out stop words and get meaningful words
    meaningful_words = [word for word in words if word not in stop_words and len(word) > 1]
    unique_meaningful_words = set(meaningful_words)

    # Calculate word frequency for meaningful words
    word_freq = Counter(meaningful_words).most_common(5)

    # Find repeated phrases (3 words)
    phrases = []
    for i in range(len(words)-2):
        phrase = ' '.join(words[i:i+3])
        phrases.append(phrase)
    repeated_phrases = [phrase for phrase, count in Counter(phrases).most_common(3) if count > 1]

    # Calculate vocabulary richness using meaningful words only
    vocabulary_richness = len(unique_meaningful_words) / len(meaningful_words) * 100 if meaningful_words else 0

    return {
        'total_lines': line_count,
        'total_words': word_count,
        'unique_words': len(unique_meaningful_words),
        'meaningful_words': len(meaningful_words),
        'top_words': word_freq,
        'repeated_phrases': repeated_phrases,
        'vocabulary_richness': round(vocabulary_richness, 2)
    }

def format_statistics(stats: Dict) -> str:
    """Format song statistics into a readable message."""
    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    # Format top words with emoji numbers
    top_words_formatted = "\n".join(
        f"{emoji} {word}: {count} times"
        for emoji, (word, count) in zip(emoji_numbers, stats['top_words'])
    )

    return (
        "📊 Song Statistics:\n\n"
        f"📝 Lines: {stats['total_lines']}\n"
        f"📚 Total Words: {stats['total_words']}\n"
        f"🎯 Unique Words: {stats['unique_words']}\n"
        f"🔤 Meaningful Words: {stats['meaningful_words']}\n"
        f"🎨 Vocabulary Richness: {stats['vocabulary_richness']}%\n\n"
        "🔝 Most Used Words:\n" +
        top_words_formatted +
        "\n\n📎 Most Repeated Phrases:\n" +
        "\n".join(f"• \"{phrase}\"" for phrase in stats['repeated_phrases'][:3])
    )

def format_lyrics(lyrics: str) -> str:
    """Format lyrics for Telegram message."""
    if not lyrics:
        return "No lyrics available."

    # Remove empty lines and clean up formatting
    formatted = []
    for line in lyrics.split('\n'):
        line = line.strip()
        if line:
            # Handle common formatting issues
            line = line.replace('[', '「').replace(']', '」')  # Replace brackets with Japanese quotes
            line = line.replace('  ', ' ')  # Remove double spaces
            formatted.append(line)

    return '\n'.join(formatted)

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

def analyze_rhyme_pattern(lyrics: str) -> Dict:
    """Analyze rhyme patterns in lyrics."""
    import re
    from collections import defaultdict

    # Split into lines and clean up
    lines = [line.strip().lower() for line in lyrics.split('\n') if line.strip()]

    # Extract last word of each line
    last_words = []
    for line in lines:
        words = re.findall(r'\b\w+\b', line)
        if words:
            last_words.append(words[-1])

    # Find rhyming patterns
    rhyme_groups = defaultdict(list)
    for i, word1 in enumerate(last_words):
        if len(word1) < 2:  # Skip very short words
            continue

        # Check for perfect rhymes (same ending)
        suffix = word1[-2:]  # Use last two characters for simple rhyme detection
        rhyme_groups[suffix].append(i + 1)  # Store line numbers (1-based)

    # Filter out non-rhyming words
    rhyme_patterns = {suffix: lines for suffix, lines in rhyme_groups.items() if len(lines) > 1}

    return {
        'total_lines': len(lines),
        'rhyming_lines': sum(len(lines) for lines in rhyme_patterns.values()),
        'rhyme_density': round(sum(len(lines) for lines in rhyme_patterns.values()) / len(lines) * 100, 2),
        'rhyme_groups': dict(rhyme_patterns)
    }

def get_detailed_song_analysis(lyrics: str) -> Dict:
    """Get comprehensive song analysis including mood, structure, and rhymes."""
    from typing import List, Dict
    import re

    basic_stats = get_song_statistics(lyrics)
    rhyme_analysis = analyze_rhyme_pattern(lyrics)
    mood = detect_song_mood(lyrics)

    # Detect verse/chorus markers
    structure_markers = {
        'verse': len(re.findall(r'\[verse\]|\[v\d?\]', lyrics.lower())),
        'chorus': len(re.findall(r'\[chorus\]|\[ch\d?\]', lyrics.lower())),
        'bridge': len(re.findall(r'\[bridge\]', lyrics.lower())),
        'intro': len(re.findall(r'\[intro\]', lyrics.lower())),
        'outro': len(re.findall(r'\[outro\]', lyrics.lower()))
    }

    # Enhanced mood analysis
    mood_intensity = {
        'happy': sum(1 for word in re.findall(r'\b\w+\b', lyrics.lower()) 
                    if word in ['happy', 'joy', 'smile', 'laugh', 'fun', 'love']),
        'sad': sum(1 for word in re.findall(r'\b\w+\b', lyrics.lower())
                  if word in ['sad', 'cry', 'tears', 'pain', 'hurt', 'alone']),
        'energetic': sum(1 for word in re.findall(r'\b\w+\b', lyrics.lower())
                        if word in ['jump', 'dance', 'run', 'fire', 'burn', 'alive'])
    }

    return {
        'statistics': basic_stats,
        'rhyme_analysis': rhyme_analysis,
        'mood': {
            'primary_mood': mood,
            'mood_intensity': mood_intensity
        },
        'structure': structure_markers
    }

def format_detailed_analysis(analysis: Dict) -> str:
    """Format detailed song analysis into a readable message."""

    # Format rhyme analysis
    rhyme_info = (
        f"🎭 Rhyme Analysis:\n"
        f"• Rhyming Lines: {analysis['rhyme_analysis']['rhyming_lines']}/{analysis['rhyme_analysis']['total_lines']}\n"
        f"• Rhyme Density: {analysis['rhyme_analysis']['rhyme_density']}%\n"
    )

    # Format mood intensity
    mood_intensities = analysis['mood']['mood_intensity']
    dominant_intensity = max(mood_intensities.items(), key=lambda x: x[1])
    mood_info = (
        f"🎭 Mood Analysis:\n"
        f"• Primary Mood: {analysis['mood']['primary_mood'].title()}\n"
        f"• Emotional Keywords:\n"
        f"  - Happy: {mood_intensities['happy']} mentions\n"
        f"  - Sad: {mood_intensities['sad']} mentions\n"
        f"  - Energetic: {mood_intensities['energetic']} mentions\n"
    )

    # Format structure information
    structure = analysis['structure']
    structure_info = "🎼 Song Structure:\n"
    for part, count in structure.items():
        if count > 0:
            structure_info += f"• {part.title()}: {count} sections\n"

    # Format statistics
    stats = analysis['statistics']
    stats_info = (
        f"📊 Lyrical Statistics:\n"
        f"• Lines: {stats['total_lines']}\n"
        f"• Words: {stats['total_words']}\n"
        f"• Unique Words: {stats['unique_words']}\n"
        f"• Vocabulary Richness: {stats['vocabulary_richness']}%\n"
    )

    return (
        f"{stats_info}\n"
        f"{rhyme_info}\n"
        f"{mood_info}\n"
        f"{structure_info}\n"
        "Want to explore more? Try these commands:\n"
        "• /lyrics - Get full lyrics\n"
        "• /recommend - Find similar songs\n"
        "• /quiz - Test your knowledge"
    )