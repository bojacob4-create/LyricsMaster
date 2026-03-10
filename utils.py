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
    richness = stats['vocabulary_richness']
    if richness >= 80:
        richness_label = "Very diverse"
    elif richness >= 60:
        richness_label = "Diverse"
    elif richness >= 40:
        richness_label = "Moderate"
    else:
        richness_label = "Repetitive"

    top_words_formatted = "\n".join(
        f"  {word} ({count}x)"
        for word, count in stats['top_words']
    )

    phrases_formatted = "\n".join(
        f"  \"{phrase}\""
        for phrase in stats['repeated_phrases'][:3]
    ) if stats['repeated_phrases'] else "  No repeated phrases found"

    return (
        "📊 Lyrical Statistics\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 {stats['total_lines']} lines  •  {stats['total_words']} words\n"
        f"🎯 {stats['unique_words']} unique words out of {stats['meaningful_words']} meaningful\n"
        f"🎨 Vocabulary richness: {stats['vocabulary_richness']}% — {richness_label}\n\n"
        "🔝 Most Used Words:\n" +
        top_words_formatted +
        "\n\n📎 Repeated Phrases:\n" +
        phrases_formatted
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
    stats = analysis['statistics']
    rhyme = analysis['rhyme_analysis']
    mood_data = analysis['mood']
    structure = analysis['structure']

    richness = stats['vocabulary_richness']
    if richness >= 80:
        vocab_note = "Highly diverse vocabulary — poetic or storytelling style"
    elif richness >= 60:
        vocab_note = "Good word variety — balanced between hooks and narrative"
    elif richness >= 40:
        vocab_note = "Moderate repetition — typical pop/chorus-heavy structure"
    else:
        vocab_note = "Very repetitive — hook-driven or chant-style lyrics"

    rhyme_density = rhyme['rhyme_density']
    if rhyme_density >= 60:
        rhyme_note = "Strong rhyme patterns throughout"
    elif rhyme_density >= 30:
        rhyme_note = "Moderate rhyming — mix of rhymed and free lines"
    else:
        rhyme_note = "Mostly free-form or conversational style"

    mood_emoji = {
        'happy': '😊', 'sad': '😢', 'romantic': '💖',
        'energetic': '⚡', 'relaxed': '😌'
    }.get(mood_data['primary_mood'], '🎵')

    mood_intensities = mood_data['mood_intensity']
    mood_bars = []
    max_intensity = max(mood_intensities.values()) if mood_intensities.values() else 1
    for label, count in mood_intensities.items():
        bar_len = int((count / max(max_intensity, 1)) * 8) if count > 0 else 0
        bar = '█' * bar_len + '░' * (8 - bar_len)
        mood_bars.append(f"  {label.title():10} {bar} ({count})")

    structure_parts = []
    for part, count in structure.items():
        if count > 0:
            structure_parts.append(f"{part.title()} x{count}")

    result = (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Structure\n"
        f"  {stats['total_lines']} lines  •  {stats['total_words']} words\n"
        f"  {stats['unique_words']} unique words ({stats['vocabulary_richness']}%)\n"
        f"  → {vocab_note}\n"
    )

    if structure_parts:
        result += f"  Sections: {', '.join(structure_parts)}\n"

    result += (
        f"\n🎭 Mood: {mood_emoji} {mood_data['primary_mood'].title()}\n"
        + '\n'.join(mood_bars) + '\n'
        f"\n🎶 Rhyme Pattern\n"
        f"  {rhyme['rhyming_lines']}/{rhyme['total_lines']} lines rhyme ({rhyme_density}%)\n"
        f"  → {rhyme_note}\n"
    )

    if stats['top_words']:
        top_words = ', '.join(f"{w} ({c}x)" for w, c in stats['top_words'][:5])
        result += f"\n🔑 Key Words: {top_words}\n"

    if stats['repeated_phrases']:
        phrases = ' | '.join(f'"{p}"' for p in stats['repeated_phrases'][:3])
        result += f"\n📎 Repeated: {phrases}\n"

    result += (
        "\n━━━━━━━━━━━━━━━━━━━━━\n"
        "🎤 /lyrics for full text  •  🎵 /recommend for similar songs"
    )

    return result