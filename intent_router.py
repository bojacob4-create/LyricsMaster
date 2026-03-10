import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

YOUTUBE_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

LYRICS_KEYWORDS = [
    'lyrics', 'lyric', 'words to', 'words of', 'text of', 'text for',
    'show me the lyrics', 'get lyrics', 'find lyrics', 'what are the lyrics',
    'sing', 'how does .* go',
]

RECOMMEND_KEYWORDS = [
    'similar to', 'songs like', 'music like', 'recommend', 'suggestion',
    'what should i listen', 'something like', 'more like', 'like this',
    'what else', 'similar songs', 'similar music',
]

ARTIST_KEYWORDS = [
    'who is', 'who are', 'tell me about', 'about the artist',
    'artist info', 'info on', 'biography', 'bio of', 'about .* artist',
]

YOUTUBE_KEYWORDS = [
    'video for', 'music video', 'watch', 'show the video',
    'find the video', 'play', 'youtube',
]

DOWNLOAD_KEYWORDS = [
    'download', 'save video', 'get video', 'download video',
]

MP3_KEYWORDS = [
    'mp3', 'audio', 'convert to mp3', 'convert to audio',
    'extract audio', 'just the audio', 'as mp3',
]

TRENDING_KEYWORDS = [
    'trending', 'what.s trending', 'popular', 'top songs',
    'what.s popular', 'hot right now', 'charts', 'top music',
    'what.s hot', 'show trending', 'show popular',
]

TRANSLATE_KEYWORDS = [
    'translate', 'translated', 'translation',
    'arabic', 'in arabic', 'to arabic',
    'spanish', 'to spanish', 'in spanish',
    'french', 'to french', 'in french',
    'german', 'to german', 'in german',
    'italian', 'to italian', 'in italian',
    'portuguese', 'to portuguese',
    'turkish', 'to turkish',
    'russian', 'to russian',
    'japanese', 'to japanese',
    'korean', 'to korean',
    'chinese', 'to chinese',
    'hindi', 'to hindi',
]

ANALYZE_KEYWORDS = [
    'analyze', 'analysis', 'break down', 'breakdown',
    'deep dive', 'detailed analysis',
]

STATS_KEYWORDS = [
    'stats', 'statistics', 'word count', 'how many words',
]

SONG_DASHBOARD_KEYWORDS = [
    'song dashboard', 'full info', 'everything about', 'overview of',
    'all about', 'tell me everything',
]

QUIZ_KEYWORDS = [
    'quiz', 'play a game', 'guess the song', 'lyrics game',
    'start a quiz', 'music quiz',
]

RANDOM_KEYWORDS = [
    'random', 'surprise me', 'random song', 'pick a song',
    'anything', 'something random',
]

SUBSCRIBE_KEYWORDS = [
    'subscribe', 'daily songs', 'send me daily', 'daily picks',
]

UNSUBSCRIBE_KEYWORDS = [
    'unsubscribe', 'stop daily', 'no more daily',
]

FILLER_WORDS = [
    'show', 'me', 'find', 'get', 'can', 'you', 'please', 'i', 'want',
    'a', 'this', 'that', 'is', 'give', 'do', 'could', 'would',
    'some', 'the', 'right', 'now', 'songs', 'song', 'music',
]


def _match_keywords(text: str, keywords: list) -> bool:
    for kw in keywords:
        if re.search(r'\b' + kw + r'\b', text, re.IGNORECASE):
            return True
    return False


def _extract_youtube_url(text: str) -> Optional[str]:
    match = YOUTUBE_URL_PATTERN.search(text)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None


def _extract_query_after(text: str, patterns: list) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            remainder = text[match.end():].strip()
            remainder = re.sub(r'^(for|of|to|the|song)\s+', '', remainder, flags=re.IGNORECASE).strip()
            if remainder:
                return remainder
    return ''


def _normalize_song_query(raw: str) -> str:
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', raw.strip(), re.IGNORECASE)
    if by_match:
        song_part = by_match.group(1).strip()
        artist_part = by_match.group(2).strip()
        if song_part and artist_part:
            return f"{artist_part} - {song_part}"
    return raw.strip()


def _strip_filler_prefix(text: str) -> str:
    result = text
    while True:
        cleaned = re.sub(
            r'^(for|of|to|the|me|show|find|get|can|you|please|i|want|a|this|that|is|give|do|some|right|now)\s+',
            '', result, flags=re.IGNORECASE
        ).strip()
        if cleaned == result:
            break
        result = cleaned
    return result


def _strip_filler_suffix(text: str) -> str:
    result = text
    while True:
        cleaned = re.sub(
            r'\s+(on|in|at|for|to|please|now|right now)$',
            '', result, flags=re.IGNORECASE
        ).strip()
        if cleaned == result:
            break
        result = cleaned
    return result


def _clean_query(text: str, keywords_to_remove: list) -> str:
    result = text
    for kw in keywords_to_remove:
        result = re.sub(r'\b' + kw + r'\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s+', ' ', result).strip()
    result = _strip_filler_prefix(result)
    result = _strip_filler_suffix(result)
    result = _normalize_song_query(result)
    return result


def _clean_query_translate(text: str) -> str:
    import re as _re
    lang_suffix = ''
    lang_match = _re.search(r'\s+(?:to|into|in)\s+(\w+)\s*$', text, _re.IGNORECASE)
    if lang_match:
        lang_suffix = lang_match.group(0).strip()
        text = text[:lang_match.start()].strip()

    result = text
    for kw in ['translate', 'translated', 'translation', 'can you', 'please', 'i want']:
        result = _re.sub(r'\b' + kw + r'\b', '', result, flags=_re.IGNORECASE)
    result = _re.sub(r'\s+', ' ', result).strip()
    result = _strip_filler_prefix(result)
    result = _strip_filler_suffix(result)
    result = _normalize_song_query(result)

    if lang_suffix:
        result = f"{result} {lang_suffix}"
    return result


def _extract_top_genre(text: str) -> Optional[str]:
    patterns = [
        r'\btop\s+(\w+)',
        r'\bbest\s+(\w+)',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            genre = match.group(1).lower()
            if genre in ('songs', 'song', 'music', 'tracks'):
                continue
            return genre

    patterns_with_suffix = [
        r'\btop\s+(\w+)\s+(?:songs?|music|tracks?)',
        r'\bbest\s+(\w+)\s+(?:songs?|music|tracks?)',
        r'(?:show|give)\s+(?:me\s+)?top\s+(\w+)',
        r'(?:show|give)\s+(?:me\s+)?best\s+(\w+)',
    ]
    for pat in patterns_with_suffix:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            genre = match.group(1).lower()
            if genre not in ('songs', 'song', 'music', 'tracks', 'the', 'me', 'some'):
                return genre

    return None


def detect_intent(text: str) -> Tuple[Optional[str], str]:
    text = text.strip()

    if not text or text.startswith('/'):
        return None, ''

    yt_url = _extract_youtube_url(text)
    if yt_url:
        if _match_keywords(text, MP3_KEYWORDS):
            return 'mp3', yt_url
        return 'download', yt_url

    if _match_keywords(text, UNSUBSCRIBE_KEYWORDS):
        return 'unsubscribe', ''

    if _match_keywords(text, SUBSCRIBE_KEYWORDS):
        return 'subscribe', ''

    if _match_keywords(text, QUIZ_KEYWORDS):
        return 'quiz', ''

    if _match_keywords(text, RANDOM_KEYWORDS):
        return 'random', ''

    if _match_keywords(text, TRENDING_KEYWORDS):
        genre = _extract_top_genre(text)
        if genre:
            return 'top', genre
        return 'trending', ''

    genre = _extract_top_genre(text)
    if genre:
        return 'top', genre

    if _match_keywords(text, TRANSLATE_KEYWORDS):
        query = _clean_query_translate(text)
        return 'translate', query

    if _match_keywords(text, ANALYZE_KEYWORDS):
        query = _clean_query(text, ['analyze', 'analysis', 'break down', 'breakdown', 'deep dive', 'detailed'])
        return 'analyze', query

    if _match_keywords(text, STATS_KEYWORDS):
        query = _clean_query(text, ['stats', 'statistics', 'word count', 'how many words'])
        return 'stats', query

    if _match_keywords(text, RECOMMEND_KEYWORDS):
        query = _clean_query(text, ['similar', 'songs like', 'music like', 'recommend', 'recommendation',
                                     'suggestion', 'something like', 'more like', 'like this',
                                     'what else', 'similar songs', 'similar music', 'like'])
        return 'recommend', query

    if _match_keywords(text, ARTIST_KEYWORDS):
        query = _extract_query_after(text, [r'who is\s*', r'who are\s*', r'tell me about\s*',
                                            r'about\s*', r'info on\s*', r'bio of\s*'])
        if not query:
            query = _clean_query(text, ['who', 'is', 'are', 'tell', 'about', 'artist', 'info', 'biography', 'bio'])
        return 'artist', query

    if _match_keywords(text, YOUTUBE_KEYWORDS):
        query = _clean_query(text, ['video', 'music video', 'watch', 'play', 'youtube',
                                     'show', 'find'])
        return 'youtube', query

    if _match_keywords(text, SONG_DASHBOARD_KEYWORDS):
        query = _clean_query(text, ['song dashboard', 'full info', 'everything about',
                                     'overview', 'all about', 'tell', 'everything'])
        return 'song', query

    if _match_keywords(text, LYRICS_KEYWORDS):
        query = _clean_query(text, ['lyrics', 'lyric', 'words', 'text', 'sing',
                                     'how does', 'go'])
        return 'lyrics', query

    if _match_keywords(text, DOWNLOAD_KEYWORDS):
        query = _clean_query(text, ['download', 'save', 'get'])
        return 'download', query

    return None, text
