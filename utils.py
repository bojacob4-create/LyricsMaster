from typing import List, Dict, Tuple
import re
import json as _json
import os as _os
import threading as _threading
from collections import Counter, defaultdict


# ── Atomic JSON state writes (round 6 QA) ──────────────────────────────────
# Several features persist state to JSON (quiz scores, subscribers, MP3
# file_ids, duels). A crash mid-write used to corrupt the file, and
# concurrent read-modify-write cycles could clobber each other. All state
# writes go through these helpers: per-path lock + tmp file + atomic rename.
_json_write_locks = {}
_json_write_locks_guard = _threading.Lock()


def _json_lock_for(path: str):
    with _json_write_locks_guard:
        lock = _json_write_locks.get(path)
        if lock is None:
            lock = _json_write_locks[path] = _threading.Lock()
        return lock


def atomic_json_write(path: str, data, **dump_kwargs) -> bool:
    """Write JSON atomically (tmp + rename) under a per-path lock."""
    lock = _json_lock_for(path)
    with lock:
        try:
            tmp = f"{path}.tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                _json.dump(data, f, **dump_kwargs)
            _os.replace(tmp, path)
            return True
        except Exception:
            try:
                _os.remove(tmp)
            except Exception:
                pass
            return False


def locked_json_update(path: str, update_fn, default=None, **dump_kwargs):
    """Load JSON, apply update_fn(data)->new_data, save atomically.

    The whole read-modify-write runs under the per-path lock, so concurrent
    quiz finishes / duel updates can't clobber each other. Returns the new
    data, or None if the write failed.
    """
    lock = _json_lock_for(path)
    with lock:
        data = default if default is not None else {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass
        try:
            new_data = update_fn(data)
        except Exception:
            return None
        try:
            tmp = f"{path}.tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                _json.dump(new_data, f, **dump_kwargs)
            _os.replace(tmp, path)
            return new_data
        except Exception:
            try:
                _os.remove(tmp)
            except Exception:
                pass
            return None


def escape_markdown(text: str) -> str:
    """Escape Telegram MarkdownV1 special chars in dynamic (user/provider) text.

    Song/artist names come from users and providers and can contain _, *, `,
    [ — any of which breaks parse_mode='Markdown' sends (BadRequest) or
    garbles rendering. Static template text with deliberate formatting must
    NOT go through this.
    """
    if not text:
        return ''
    return re.sub(r'([_*`\[\]])', r'\\\1', str(text))


def get_song_statistics(lyrics: str) -> Dict:
    """
    Analyze song lyrics and return interesting statistics.

    Args:
        lyrics (str): Song lyrics to analyze

    Returns:
        Dict: Statistics including word count, unique words, common words, etc.
    """
    # Guard: pure function must never raise on empty/None input — it is called
    # from live paths (stats, song dashboard, analysis) where a lyric-provider
    # hiccup can hand us nothing.
    if not lyrics or not lyrics.strip():
        return {
            'total_lines': 0,
            'total_words': 0,
            'unique_words': 0,
            'meaningful_words': 0,
            'top_words': [],
            'repeated_phrases': [],
            'vocabulary_richness': 0.0,
        }
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
    lyrics_clean = re.sub(r"'(?!(ve|re|ll|s|m|d|t)\b)", " ", lyrics_clean)
    # Remove other punctuation except apostrophes
    lyrics_clean = re.sub(r'[^\w\s\']', ' ', lyrics_clean)
    # Replace multiple spaces with single space
    lyrics_clean = re.sub(r'\s+', ' ', lyrics_clean)

    # Get all words, keeping contractions intact.
    # Unicode-aware: accented letters (é, ñ, …) count as part of the word
    # instead of silently dropping the whole word from the count.
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*", lyrics_clean)
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

MOOD_KEYWORDS = {
    'happy': [
        'happy', 'joy', 'smile', 'laugh', 'fun', 'dance', 'party', 'sunshine',
        'celebrate', 'cheer', 'bright', 'glad', 'wonderful', 'amazing', 'good',
        'great', 'beautiful day', 'feeling good', 'blessed', 'alive', 'yeah',
        'exciting', 'hooray', 'woo', 'yay',
    ],
    'sad': [
        'sad', 'cry', 'tears', 'pain', 'hurt', 'alone', 'lost', 'sorry', 'missing',
        'gone', 'broken', 'break', 'goodbye', 'leave', 'left', 'empty', 'dark',
        'hollow', 'miss', 'regret', 'suffer', 'wound', 'drown', 'fall', 'fade',
        'cold', 'rain', 'shadow', 'numb', 'helpless', 'sorrow', 'grief', 'dying',
        'apart', 'over', 'end', 'wrong',
    ],
    'romantic': [
        'love', 'heart', 'kiss', 'beautiful', 'forever', 'darling', 'romance',
        'baby', 'honey', 'sweetheart', 'hold', 'touch', 'feel', 'close',
        'desire', 'passion', 'tender', 'embrace', 'adore', 'devotion', 'lover',
        'mine', 'yours', 'together', 'need you', 'want you', 'arms', 'eyes',
        'lips', 'skin', 'body', 'breathe',
    ],
    'energetic': [
        'jump', 'run', 'fire', 'burn', 'wild', 'free', 'tonight',
        'fight', 'power', 'strong', 'fast', 'loud', 'scream', 'shout',
        'bang', 'blast', 'explode', 'rage', 'rush', 'move', 'go',
        'let\'s go', 'come on', 'turn up', 'rise', 'unstoppable', 'harder',
        'faster', 'push', 'break free',
    ],
    'relaxed': [
        'peace', 'calm', 'quiet', 'dream', 'sleep', 'gentle', 'slow',
        'easy', 'breathe', 'soft', 'still', 'float', 'drift', 'rest',
        'serene', 'breeze', 'ocean', 'sky', 'clouds', 'light', 'warm',
        'home', 'safe', 'soothe', 'lullaby', 'whisper',
    ],
}


def _count_mood_hits(lyrics_lower: str, normalize: bool = False) -> Dict:
    """Count mood-keyword hits per mood.

    With normalize=True each mood's count is scaled by
    (average keyword-list size / that mood's list size), so moods that
    simply have longer keyword lists don't win by default.
    """
    counts = {}
    avg_list_size = (
        sum(len(kw) for kw in MOOD_KEYWORDS.values()) / len(MOOD_KEYWORDS)
    )
    for mood, keywords in MOOD_KEYWORDS.items():
        total = 0
        for kw in keywords:
            total += len(re.findall(r'\b' + re.escape(kw) + r'\b', lyrics_lower))
        if normalize and keywords:
            total = total * avg_list_size / len(keywords)
        counts[mood] = total
    return counts


def detect_song_mood(lyrics: str) -> str:
    """Detect the mood of a song based on its lyrics.

    Hit counts are normalized by keyword-list size so every mood competes
    on equal footing.
    """
    mood_counts = _count_mood_hits(lyrics.lower(), normalize=True)
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

    # Guard: empty input would divide by zero below.
    if not lyrics or not lyrics.strip():
        return {
            'total_lines': 0,
            'rhyming_lines': 0,
            'rhyme_density': 0.0,
            'rhyme_groups': {},
        }

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

    lyrics_lower = lyrics.lower()
    # Normalized by keyword-list size (see _count_mood_hits) so the bars are
    # comparable across moods.
    mood_counts = _count_mood_hits(lyrics_lower, normalize=True)

    total_words = max(len(re.findall(r'\b\w+\b', lyrics_lower)), 1)
    mood_intensity = {}
    for m, raw in mood_counts.items():
        density = raw / total_words
        score = min(10, round(density * 200))
        mood_intensity[m] = score

    max_score = max(mood_intensity.values()) if mood_intensity else 0
    if max_score > 0 and max_score < 5:
        scale = 7 / max(max_score, 1)
        for m in mood_intensity:
            mood_intensity[m] = min(10, round(mood_intensity[m] * scale))

    themes = detect_themes(lyrics)

    return {
        'statistics': basic_stats,
        'rhyme_analysis': rhyme_analysis,
        'mood': {
            'primary_mood': mood,
            'mood_intensity': mood_intensity
        },
        'structure': structure_markers,
        'themes': themes,
    }


def detect_themes(lyrics: str) -> List[str]:
    lyrics_lower = lyrics.lower()
    words = set(re.findall(r'\b\w+\b', lyrics_lower))

    theme_keywords = {
        'romantic': {'love', 'kiss', 'heart', 'darling', 'baby', 'honey', 'sweetheart', 'lover', 'romance', 'adore', 'devotion', 'embrace', 'tender'},
        'sensual': {'body', 'touch', 'skin', 'lips', 'desire', 'heat', 'sweat', 'close', 'taste', 'breathe', 'feeling', 'hot', 'wet'},
        'heartbreak': {'broke', 'broken', 'goodbye', 'leave', 'left', 'gone', 'miss', 'regret', 'apart', 'over', 'end', 'letting'},
        'longing': {'miss', 'wish', 'remember', 'memories', 'again', 'return', 'waiting', 'distance', 'far', 'someday', 'hope'},
        'confidence': {'boss', 'queen', 'king', 'power', 'strong', 'unstoppable', 'fearless', 'own', 'shine', 'crown', 'flex', 'win', 'best'},
        'celebration': {'party', 'dance', 'tonight', 'celebrate', 'cheers', 'vibe', 'festival', 'drink', 'club', 'turn', 'lit'},
        'introspective': {'think', 'wonder', 'question', 'soul', 'meaning', 'inside', 'reflect', 'truth', 'searching', 'understand', 'mind', 'thought'},
        'motivational': {'rise', 'fight', 'believe', 'dream', 'strength', 'never', 'give', 'stand', 'keep', 'brave', 'overcome', 'forward'},
        'nostalgic': {'remember', 'young', 'childhood', 'past', 'used', 'days', 'old', 'time', 'memories', 'back', 'years', 'ago'},
        'rebellious': {'break', 'rules', 'rebel', 'free', 'wild', 'chaos', 'destroy', 'system', 'fight', 'resist', 'against'},
        'melancholic': {'rain', 'tears', 'dark', 'shadow', 'cold', 'empty', 'fading', 'drown', 'hollow', 'numb', 'grey', 'silence'},
        'empowerment': {'woman', 'man', 'independent', 'myself', 'enough', 'worth', 'proud', 'beautiful', 'real', 'authentic', 'unapologetic'},
        'spiritual': {'god', 'heaven', 'pray', 'faith', 'angel', 'blessed', 'divine', 'sacred', 'spirit', 'grace', 'miracle'},
        'street': {'money', 'hustle', 'grind', 'hood', 'block', 'real', 'trap', 'gang', 'ride', 'stack', 'drip'},
    }

    theme_scores = {}
    for theme, keywords in theme_keywords.items():
        overlap = words & keywords
        if overlap:
            score = 0
            for kw in overlap:
                score += len(re.findall(r'\b' + kw + r'\b', lyrics_lower))
            theme_scores[theme] = score

    if not theme_scores:
        return ['general']

    sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    for theme, score in sorted_themes:
        if score >= 2 or (not result and score >= 1):
            result.append(theme)
        if len(result) >= 3:
            break

    return result if result else ['general']

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

    mood_scores = mood_data['mood_intensity']
    mood_bars = []
    mood_order = ['happy', 'sad', 'romantic', 'energetic', 'relaxed']
    mood_emojis = {'happy': '😊', 'sad': '😢', 'romantic': '💖', 'energetic': '⚡', 'relaxed': '😌'}
    for label in mood_order:
        score = mood_scores.get(label, 0)
        bar = '█' * score + '░' * (10 - score)
        emoji = mood_emojis.get(label, '🎵')
        mood_bars.append(f"  {emoji} {label.title():10} {bar}  {score}/10")

    structure_parts = []
    for part, count in structure.items():
        if count > 0:
            structure_parts.append(f"{part.title()} x{count}")

    result = (
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Structure\n"
        f"  {stats['total_lines']} lines  •  {stats['total_words']} words\n"
        f"  {stats['unique_words']} unique meaningful words ({stats['vocabulary_richness']}% of meaningful)\n"
        f"  → {vocab_note}\n"
    )

    if structure_parts:
        result += f"  Sections: {', '.join(structure_parts)}\n"

    result += (
        f"\n🎭 Mood: {mood_emoji} {mood_data['primary_mood'].title()}\n"
        + '\n'.join(mood_bars) + '\n'
    )

    themes = analysis.get('themes') or []
    if themes and themes != ['general']:
        themes_fmt = ', '.join(t.replace('_', ' ').title() for t in themes)
        result += f"\n🎨 Themes: {themes_fmt}\n"

    result += (
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