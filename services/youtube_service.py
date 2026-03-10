import logging
import requests
import re
from typing import Optional
from urllib.parse import quote
from functools import lru_cache

logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})


@lru_cache(maxsize=200)
def get_youtube_link(artist: str, song: str) -> Optional[str]:
    try:
        query = f"{artist} {song} official music video"
        encoded_query = quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"

        r = session.get(search_url, timeout=10)
        if r.status_code == 200:
            video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
            if video_ids:
                video_id = video_ids[0]
                return f"https://www.youtube.com/watch?v={video_id}"

        query2 = f"{artist} {song} audio"
        encoded_query2 = quote(query2)
        search_url2 = f"https://www.youtube.com/results?search_query={encoded_query2}"

        r2 = session.get(search_url2, timeout=10)
        if r2.status_code == 200:
            video_ids2 = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r2.text)
            if video_ids2:
                video_id = video_ids2[0]
                return f"https://www.youtube.com/watch?v={video_id}"

        return f"https://www.youtube.com/results?search_query={encoded_query}"

    except Exception as e:
        logger.error(f"Error getting YouTube link: {e}")
        return f"https://www.youtube.com/results?search_query={quote(f'{artist} {song}')}"


def format_youtube_response(artist: str, song: str, url: str) -> str:
    is_direct = 'watch?v=' in url

    if is_direct:
        return (
            f"🎬 {artist} — {song}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"▶️ Watch now:\n{url}\n\n"
            f"🎤 /lyrics {artist} - {song}\n"
            f"📊 /analyze {artist} - {song}"
        )
    else:
        return (
            f"🎬 {artist} — {song}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔍 Search results:\n{url}\n\n"
            f"Tip: The first result is usually the official video.\n\n"
            f"🎤 /lyrics {artist} - {song}\n"
            f"📊 /analyze {artist} - {song}"
        )
