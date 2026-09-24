import logging
import requests
import re
import json
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote
from functools import lru_cache

logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})


def _normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9\s]', '', text.lower()).strip()


def _extract_candidates(html: str) -> List[Dict]:
    candidates = []
    match = re.search(r'var ytInitialData = ({.*?});', html)
    if match:
        try:
            data = json.loads(match.group(1))
            contents = (data.get('contents', {})
                        .get('twoColumnSearchResultsRenderer', {})
                        .get('primaryContents', {})
                        .get('sectionListRenderer', {})
                        .get('contents', []))
            for section in contents:
                items = section.get('itemSectionRenderer', {}).get('contents', [])
                for item in items:
                    vr = item.get('videoRenderer', {})
                    if not vr:
                        continue
                    vid = vr.get('videoId', '')
                    title = vr.get('title', {}).get('runs', [{}])[0].get('text', '')
                    channel = vr.get('ownerText', {}).get('runs', [{}])[0].get('text', '')
                    if vid and title:
                        candidates.append({
                            'id': vid,
                            'title': title,
                            'channel': channel,
                        })
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"JSON parse error: {e}")

    if not candidates:
        ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        seen = set()
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                candidates.append({'id': vid, 'title': '', 'channel': ''})
            if len(candidates) >= 10:
                break

    return candidates[:10]


def _score_candidate(candidate: Dict, artist: str, song: str) -> int:
    title = _normalize(candidate['title'])
    channel = _normalize(candidate['channel'])
    artist_n = _normalize(artist)
    song_n = _normalize(song)

    score = 0

    if song_n and song_n in title:
        score += 50
    if artist_n and artist_n in title:
        score += 30
    if artist_n and artist_n in channel:
        score += 20

    title_lower = candidate['title'].lower()
    if 'official music video' in title_lower:
        score += 25
    elif 'official video' in title_lower:
        score += 22
    elif 'official audio' in title_lower:
        score += 18
    elif 'official lyric' in title_lower or 'lyrics' in title_lower:
        score += 15
    elif 'audio' in title_lower:
        score += 10

    reject_patterns = [
        'reaction', 'review', 'tutorial', 'cover by', 'karaoke',
        'instrumental', 'remix by', 'mashup', 'parody', 'behind the scenes',
        'interview', 'podcast', 'explained', 'how to', 'compilation',
        'top 10', 'ranking', 'tier list',
        # Reaction-video phrasings the bare 'reaction' substring misses:
        # "Twins React to X (Official Music Video)" etc.  Kept as phrases
        # (not bare 'react') so a song genuinely titled "React" is safe.
        'react to', 'reacts to', 'reaction to', 'reacting to',
    ]
    for pattern in reject_patterns:
        if pattern in title_lower:
            score -= 50

    if 'live' in title_lower and 'official' not in title_lower:
        score -= 10

    if song_n and artist_n:
        combined = f"{artist_n} {song_n}"
        if combined in title or f"{song_n} {artist_n}" in title:
            score += 15

    return score


@lru_cache(maxsize=200)
def get_youtube_link(artist: str, song: str) -> Optional[str]:
    try:
        search_terms = []
        if artist and song:
            search_terms.append(f"{artist} {song} official music video")
            search_terms.append(f"{artist} {song}")
        elif artist:
            search_terms.append(f"{artist} official music video")
        elif song:
            search_terms.append(f"{song} official music video")
        else:
            return None

        best_candidate = None
        best_score = -100

        for query in search_terms:
            encoded_query = quote(query)
            search_url = f"https://www.youtube.com/results?search_query={encoded_query}"

            r = session.get(search_url, timeout=5)
            if r.status_code != 200:
                continue

            candidates = _extract_candidates(r.text)

            for candidate in candidates:
                s = _score_candidate(candidate, artist, song)
                logger.debug(f"YT candidate: [{candidate['id']}] {candidate['title']} score={s}")
                if s > best_score:
                    best_score = s
                    best_candidate = candidate

            if best_score >= 50:
                break

        if best_candidate and best_score >= 20:
            url = f"https://www.youtube.com/watch?v={best_candidate['id']}"
            logger.info(f"YT match: '{best_candidate['title']}' score={best_score}")
            return url

        fallback_query = f"{artist} {song}".strip()
        return f"https://www.youtube.com/results?search_query={quote(fallback_query)}"

    except Exception as e:
        logger.error(f"Error getting YouTube link: {e}")
        return f"https://www.youtube.com/results?search_query={quote(f'{artist} {song}')}"


def format_youtube_response(artist: str, song: str, url: str) -> str:
    is_direct = 'watch?v=' in url
    title = f"{artist} — {song}" if song else artist
    query_ref = f"{artist} - {song}" if song else artist

    if is_direct:
        return (
            f"🎬 {title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"▶️ Watch now:\n{url}\n\n"
            f"🎤 /lyrics {query_ref}\n"
            f"📊 /analyze {query_ref}"
        )
    else:
        return (
            f"🎬 {title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔍 Search results:\n{url}\n\n"
            f"Tip: The first result is usually the official video.\n\n"
            f"🎤 /lyrics {query_ref}\n"
            f"📊 /analyze {query_ref}"
        )
