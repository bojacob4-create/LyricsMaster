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
    'translate', 'arabic', 'in arabic', 'translation',
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

TOP_KEYWORDS = [
    'top afrobeats', 'top pop', 'top rap', 'top rock', 'top rnb',
    'top latin', 'top country', 'top kpop', 'best afrobeats',
    'best pop', 'best rap', 'genre',
]

SUBSCRIBE_KEYWORDS = [
    'subscribe', 'daily songs', 'send me daily', 'daily picks',
]

UNSUBSCRIBE_KEYWORDS = [
    'unsubscribe', 'stop daily', 'no more daily',
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
            remainder = re.sub(r'^(for|of|to|the|song|by)\s+', '', remainder, flags=re.IGNORECASE).strip()
            if remainder:
                return remainder
    return ''


def _clean_query(text: str, keywords_to_remove: list) -> str:
    result = text
    for kw in keywords_to_remove:
        result = re.sub(r'\b' + kw + r'\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s+', ' ', result).strip()
    while True:
        cleaned = re.sub(r'^(for|of|to|the|me|show|find|get|can|you|please|i|want|a|this|that|is)\s+', '', result, flags=re.IGNORECASE).strip()
        if cleaned == result:
            break
        result = cleaned
    return result


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
        return 'trending', ''

    if _match_keywords(text, TRANSLATE_KEYWORDS):
        query = _clean_query(text, ['translate', 'translation', 'arabic', 'in arabic', 'to arabic'])
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

    for kw in TOP_KEYWORDS:
        match = re.search(r'\btop\s+(\w+)', text, re.IGNORECASE)
        if match:
            genre = match.group(1)
            return 'top', genre
        match2 = re.search(r'\bbest\s+(\w+)', text, re.IGNORECASE)
        if match2:
            genre = match2.group(1)
            return 'top', genre
        break

    if _match_keywords(text, LYRICS_KEYWORDS):
        query = _clean_query(text, ['lyrics', 'lyric', 'words', 'text', 'sing',
                                     'how does', 'go'])
        return 'lyrics', query

    if _match_keywords(text, DOWNLOAD_KEYWORDS):
        query = _clean_query(text, ['download', 'save', 'get'])
        return 'download', query

    return None, text
