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


# ── Round 27: video-kind classification ─────────────────────────────────────
# The video pipeline was match-and-present: best artist+title overlap won and
# was handed over as THE video, with no notion of what KIND of video it is.
# Whenever the only match is a live recording (covers, concert-only songs,
# unreleased tracks, classical/jazz…), the user got a live video passed off
# silently as the video.  Now the winner is classified and, when it is a
# non-official live performance, presented honestly (labeled live + a note +
# the original artist's official video when one surfaces).

_LIVE_MARKERS = [
    r'\blive\b', r'\blive at\b', r'\blive from\b', r'\blive in\b',
    r'\(live\)', r'\[live\]',
    r'\blive version\b', r'\blive performance\b', r'\blive concert\b',
    r'\bin concert\b', r'\bunplugged\b', r'\btiny desk\b', r'\blive lounge\b',
    r'\bfestival\b', r'\bfest\b', r'\bconcert\b', r'\btour\b',
    r'\bsession\b', r'\bsessions\b', r'\bnpr\b', r'\bvevo live\b',
    r'\bacoustic live\b',
]
_OFFICIAL_MARKERS = [
    'official music video', 'official video', 'official audio',
    'official lyric video', 'official lyrics video',
]
_LYRIC_MARKERS = [
    'lyric video', 'lyrics video', 'official lyric', 'lyrics',
]


def _classify_video_kind(video_title: str, channel: str = '',
                         artist: str = '', song: str = '') -> Dict:
    """Classify a winning video as official / live / lyric / other.

    The known song/artist names are stripped from the video title FIRST, so
    a song genuinely titled e.g. "Live Like You Were Dying" — or the band
    named "Live" — never false-positives as a live performance.
    """
    title_lower = (video_title or '').lower()
    channel_lower = (channel or '').lower()

    # Strip the known artist/song so their own words can't trip the markers.
    remainder = title_lower
    for name in (song, artist):
        n = _normalize(name or '')
        if n:
            remainder = remainder.replace(n, ' ')
    remainder = _normalize(remainder)

    is_live = any(re.search(p, remainder) for p in _LIVE_MARKERS)
    # "Official Live Video": the channel marked a live performance official.
    is_official = (any(m in title_lower for m in _OFFICIAL_MARKERS)
                   or ('official' in title_lower and is_live)
                   or 'vevo' in channel_lower
                   or channel_lower.rstrip().endswith('official'))
    is_lyric = (not is_live and not is_official
                and any(m in title_lower for m in _LYRIC_MARKERS))

    if is_live:
        kind = 'live'
    elif is_official:
        kind = 'official'
    elif is_lyric:
        kind = 'lyric'
    else:
        kind = 'other'
    return {'kind': kind, 'is_live': is_live, 'is_official': is_official}


def _fetch_candidates(query: str) -> List[Dict]:
    """One YouTube search → scored-candidate dicts (test seam)."""
    try:
        search_url = (f"https://www.youtube.com/results?search_query="
                      f"{quote(query)}")
        r = session.get(search_url, timeout=5)
        if r.status_code != 200:
            return []
        return _extract_candidates(r.text)
    except Exception as e:
        logger.debug(f"YT search failed for {query!r}: {e}")
        return []


def _search_best(artist: str, song: str, queries: List[str],
                 min_score: int = 20) -> Tuple[Optional[Dict], int,
                                               List[Dict]]:
    """Run queries in order, return (best_candidate, best_score, all_seen)."""
    best_candidate, best_score, seen = None, -100, []
    for query in queries:
        for candidate in _fetch_candidates(query):
            seen.append(candidate)
            s = _score_candidate(candidate, artist, song)
            logger.debug(f"YT candidate: [{candidate['id']}] "
                         f"{candidate['title']} score={s}")
            if s > best_score:
                best_score, best_candidate = s, candidate
        if best_score >= 50:
            break
    if best_candidate and best_score >= min_score:
        return best_candidate, best_score, seen
    return None, best_score, seen


def _find_official_alt(song: str, artist: str) -> Optional[Dict]:
    """Cover case: title-only search for an official video by another artist.

    Only used when the winner is a non-official live performance.  Returns
    {'url', 'artist', 'title'} or None.  The other artist is never asserted
    to be "the original" — it is offered as an alternative.
    """
    if not song:
        return None
    song_n = _normalize(song)
    artist_n = _normalize(artist or '')
    best, best_score = None, -100
    for candidate in _fetch_candidates(f"{song} official music video"):
        title = candidate.get('title', '')
        channel = candidate.get('channel', '')
        t_lower = title.lower()
        if not title or song_n not in _normalize(title):
            continue
        # Must look genuinely official…
        if not any(m in t_lower for m in _OFFICIAL_MARKERS):
            continue
        # …and must be somebody else's video, not the same artist's.
        if artist_n and (artist_n in _normalize(title)
                         or artist_n in _normalize(channel)):
            continue
        s = _score_candidate(candidate, '', song)
        if s > best_score:
            best, best_score = candidate, s
    if best and best_score >= 20:
        alt_artist = best['title'].split('-')[0].split('–')[0].strip()
        url = f"https://www.youtube.com/watch?v={best['id']}"
        logger.info(f"YT alt: '{best['title']}' score={best_score}")
        return {'url': url, 'artist': alt_artist, 'title': best['title']}
    return None


@lru_cache(maxsize=200)
def get_youtube_link_info(artist: str, song: str) -> Dict:
    """Choke point for video lookup.  Returns a dict:

        {'url', 'title', 'kind', 'is_live', 'is_official',
         'alt': {'url', 'artist', 'title'} | None}

    'kind' is one of official/live/lyric/other/none ('none' = fell back to
    a search-results URL, same as get_youtube_link always did).
    """
    try:
        queries = []
        if artist and song:
            queries.append(f"{artist} {song} official music video")
            queries.append(f"{artist} {song}")
        elif artist:
            queries.append(f"{artist} official music video")
        elif song:
            queries.append(f"{song} official music video")
        else:
            return {'url': None, 'title': '', 'kind': 'none',
                    'is_live': False, 'is_official': False, 'alt': None}

        best, best_score, _ = _search_best(artist, song, queries)

        if best:
            url = f"https://www.youtube.com/watch?v={best['id']}"
            cls = _classify_video_kind(best['title'], best.get('channel', ''),
                                       artist, song)
            logger.info(f"YT match: '{best['title']}' score={best_score} "
                        f"kind={cls['kind']}")
            alt = None
            if cls['is_live'] and not cls['is_official']:
                alt = _find_official_alt(song, artist)
            return {'url': url, 'title': best['title'], 'kind': cls['kind'],
                    'is_live': cls['is_live'],
                    'is_official': cls['is_official'], 'alt': alt}

        fallback = (f"https://www.youtube.com/results?search_query="
                    f"{quote(f'{artist} {song}'.strip())}")
        return {'url': fallback, 'title': '', 'kind': 'none',
                'is_live': False, 'is_official': False, 'alt': None}

    except Exception as e:
        logger.error(f"Error getting YouTube link: {e}")
        return {'url': f"https://www.youtube.com/results?search_query="
                       f"{quote(f'{artist} {song}')}",
                'title': '', 'kind': 'none',
                'is_live': False, 'is_official': False, 'alt': None}


def get_youtube_link(artist: str, song: str) -> Optional[str]:
    """URL-string wrapper around get_youtube_link_info (backward compatible)."""
    return get_youtube_link_info(artist, song).get('url')


def format_youtube_response(artist: str, song: str, url: str,
                            info: Optional[Dict] = None) -> str:
    is_direct = bool(url) and 'watch?v=' in url
    title = f"{artist} — {song}" if song else artist
    query_ref = f"{artist} - {song}" if song else artist
    info = info or {}

    # Round 27: when the winner is a non-official live performance, say so
    # instead of passing it off silently as the video.
    if is_direct and info.get('is_live') and not info.get('is_official'):
        alt = info.get('alt') or {}
        alt_block = ""
        if alt.get('url'):
            alt_block = (f"\n🎬 Also: {alt.get('artist', 'another artist')}'s "
                         f"official video:\n{alt['url']}\n")
        return (
            f"🎬 {title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎥 Live version — no official video found:\n"
            f"▶️ Watch now:\n{url}\n"
            f"{alt_block}\n"
            f"🎤 /lyrics {query_ref}\n"
            f"📊 /analyze {query_ref}"
        )

    if is_direct and info.get('is_live'):
        # Official live video (e.g. "Official Live Video") — label it, no note.
        return (
            f"🎬 {title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎥 Live version (official):\n"
            f"▶️ Watch now:\n{url}\n\n"
            f"🎤 /lyrics {query_ref}\n"
            f"📊 /analyze {query_ref}"
        )

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
