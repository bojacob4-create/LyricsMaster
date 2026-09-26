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


_ATTR_SEPS = (' - ', ' – ', ' — ', '|')


def _strip_bracket_tail(text: str) -> str:
    """Drop a trailing bracketed segment: 'Lonely (Official Video)' -> 'Lonely'."""
    return re.sub(r'\s*[\(\[].*$', '', text or '').strip()


def _title_credits_other_artist(video_title: str, artist: str, song: str) -> bool:
    """True when a video title explicitly credits a DIFFERENT artist.

    Only fires on explicit attribution structure ('ARTIST - Title',
    'Title - ARTIST', 'Title by ARTIST') whose credited names share no
    token with the requested artist.  A title with no attribution
    structure ('Lonely (Official Music Video)') never fires, so
    channel-only matches keep working exactly as before.

    Generalizes the round-13c reaction-video reject: instead of listing
    bad title patterns, reject any positive claim of the wrong artist.
    (Round 43: 'Marlon Craft - Lonely' was served as STARGUIDE's video
    on a title-only match.)
    """
    artist_tokens = set(_normalize(artist).split())
    if not artist_tokens:
        return False
    song_tokens = set(_normalize(song).split())
    t = video_title or ''

    def _tok(s: str) -> set:
        return set(_normalize(s).split())

    for sep in _ATTR_SEPS:
        if sep in t:
            head, tail = t.split(sep, 1)
            head, tail = _strip_bracket_tail(head), _strip_bracket_tail(tail)
            if not head:
                return False
            if artist_tokens & _tok(head):
                return False  # attribution agrees with the request
            if song_tokens & _tok(head):
                # 'Song - ARTIST' shape: the tail must credit our artist
                return not (artist_tokens & _tok(tail))
            return True  # head credits someone/something else entirely
    m = re.search(r'\bby\b\s+(.+)', t, flags=re.IGNORECASE)
    if m:
        return not (artist_tokens & _tok(_strip_bracket_tail(m.group(1))))
    return False


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


def _is_official_channel(channel: str) -> bool:
    """Round-79: shared official-channel signal.

    A VEVO channel or a channel name ending in 'official' is the artist's
    authoritative upload. Used by BOTH the scorer (ranking boost) and the
    kind classifier (labeling) so they can never disagree about what
    counts as an official channel.
    """
    channel_lower = (channel or '').lower()
    return ('vevo' in channel_lower
            or channel_lower.rstrip().endswith('official'))


# Round-80: reaction-video phrasings. "Twins React to X (Official Music
# Video)" mentions the official video only because it is being reacted to —
# it must never count as official itself. Kept as phrases (not bare
# 'react') so a song genuinely titled "React" is safe. One list, used by
# the scorer's penalty, the scorer's official-bonus guard, and the kind
# classifier's official guard.
_REACTION_PHRASES = ('react to', 'reacts to', 'reaction to', 'reacting to')


def _score_candidate(candidate: Dict, artist: str, song: str) -> int:
    title = _normalize(candidate['title'])
    channel = _normalize(candidate['channel'])
    artist_n = _normalize(artist)
    song_n = _normalize(song)

    # Round 43: a title that explicitly credits a different artist
    # ('Marlon Craft - Lonely' for a STARGUIDE query) is never our video,
    # no matter how well the song title matches.  Hard reject.
    if artist_n and _title_credits_other_artist(candidate['title'], artist, song):
        return -100

    score = 0

    if song_n and song_n in title:
        score += 50
    if artist_n and artist_n in title:
        score += 30
    if artist_n and artist_n in channel:
        score += 20

    title_lower = candidate['title'].lower()
    # Round-80: a reaction video's title can mention "official music video"
    # (it is reacting TO the official video) — it must not earn the
    # official-text bonus for that.
    is_reaction = any(p in title_lower for p in _REACTION_PHRASES)
    if not is_reaction:
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

    # Round-79: the artist's authoritative channel outranks fan uploads with
    # similar titles. Independent of the title-text bonuses above — a VEVO
    # upload titled plainly "Artist - Song" still counts as official.
    # (The wrong-artist hard reject above still runs first: a mismatched
    # "official" video can never leapfrog a correct match.)
    if _is_official_channel(candidate.get('channel', '')):
        score += 25

    reject_patterns = [
        'reaction', 'review', 'tutorial', 'cover by', 'karaoke',
        'instrumental', 'remix by', 'mashup', 'parody', 'behind the scenes',
        'interview', 'podcast', 'explained', 'how to', 'compilation',
        'top 10', 'ranking', 'tier list',
        # Round-80: reaction-video phrasings live in _REACTION_PHRASES now.
        *_REACTION_PHRASES,
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

    # Strip the known artist/song so their own words can't trip the markers.
    remainder = title_lower
    for name in (song, artist):
        n = _normalize(name or '')
        if n:
            remainder = remainder.replace(n, ' ')
    remainder = _normalize(remainder)

    is_live = any(re.search(p, remainder) for p in _LIVE_MARKERS)
    # "Official Live Video": the channel marked a live performance official.
    # Round-80: a reaction video mentioning "official music video" (it is
    # reacting TO the official video) is never official itself.
    is_reaction = any(p in title_lower for p in _REACTION_PHRASES)
    is_official = ((any(m in title_lower for m in _OFFICIAL_MARKERS)
                    or ('official' in title_lower and is_live)
                    or _is_official_channel(channel))
                   and not is_reaction)
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
    """Run queries in order, return (best_candidate, best_score, all_seen).

    Round-79: the early break is kind-aware. A fan lyric upload can clear
    the 50-point bar on title match alone (e.g. a brand-new release whose
    VEVO upload isn't ranking yet) — so a lyric-kind winner does NOT stop
    the search; the plain query runs and gets a chance to surface the
    official upload. When several candidates match well, an official-kind
    upload wins over a higher-scoring fan upload. Live/other winners break
    exactly as before: a concert-only track keeps its live video
    (round-27 contract).
    """
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
            # Round-79: a lyric-kind winner may be shadowing the official
            # upload (it can clear 50 on title match alone) — keep going so
            # the plain query gets a chance to surface it. Any other kind
            # breaks exactly as before.
            if _classify_video_kind(
                    best_candidate['title'],
                    best_candidate.get('channel', ''),
                    artist, song)['kind'] == 'lyric':
                continue
            break
    if best_candidate and best_score >= min_score:
        official = [c for c in seen
                    if _score_candidate(c, artist, song) >= 50
                    and _classify_video_kind(
                        c['title'], c.get('channel', ''),
                        artist, song)['kind'] == 'official']
        if official:
            best_candidate = max(
                official, key=lambda c: _score_candidate(c, artist, song))
            best_score = _score_candidate(best_candidate, artist, song)
        return best_candidate, best_score, seen
    return None, best_score, seen


def _clean_song_title(song: str) -> str:
    """Strip recording qualifiers from a song title for display.

    The song string reaching the video pipeline often carries the
    recording's qualifier ('Uninvited - Live at Newport Folk' — the
    lyrics-resolved title of the live recording the user tapped).
    Showing the full qualifier in the video response header is noisy;
    the clean title ('Uninvited') reads correctly next to the live note.

    'Uninvited - Live at Newport Folk' → 'Uninvited'
    'Hello (Live at the BRITs)'       → 'Hello'
    'Water'                           → 'Water'  (untouched)

    Only segments carrying live markers are stripped, so genuine titles
    ('Song - Studio Version') pass through unchanged.  The primary search
    keeps the full title — it is what finds the live video itself.
    """
    s = song or ''
    # A trailing ' - <live qualifier>' segment (the most common leak).
    parts = s.split(' - ')
    if len(parts) > 1:
        tail_n = _normalize(' - '.join(parts[1:]))
        if any(re.search(p, tail_n) for p in _LIVE_MARKERS):
            s = parts[0]
    # Parenthetical/bracket segments that carry live markers.
    def _strip_live_seg(m):
        seg = m.group(0)
        if any(re.search(p, _normalize(seg)) for p in _LIVE_MARKERS):
            return ' '
        return seg
    s = re.sub(r'\([^)]*\)', _strip_live_seg, s)
    s = re.sub(r'\[[^\]]*\]', _strip_live_seg, s)
    # Standalone live-marker phrases anywhere else.
    for pat in _LIVE_MARKERS:
        s = re.sub(pat, ' ', s, flags=re.IGNORECASE)
    return ' '.join(s.split()).strip()


@lru_cache(maxsize=200)
def get_youtube_link_info(artist: str, song: str) -> Dict:
    """Choke point for video lookup.  Returns a dict:

        {'url', 'title', 'kind', 'is_live', 'is_official', 'clean_song'}

    'kind' is one of official/live/lyric/other/none ('none' = fell back to
    a search-results URL, same as get_youtube_link always did).
    """
    try:
        clean_song = _clean_song_title(song)
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
                    'is_live': False, 'is_official': False,
                    'clean_song': clean_song}

        best, best_score, _ = _search_best(artist, song, queries)

        if best:
            url = f"https://www.youtube.com/watch?v={best['id']}"
            cls = _classify_video_kind(best['title'], best.get('channel', ''),
                                       artist, song)
            logger.info(f"YT match: '{best['title']}' score={best_score} "
                        f"kind={cls['kind']}")
            # A title-only search cannot reliably establish that another
            # artist's same-titled song is the covered/original work, so no
            # second-link alternative is offered anymore — a wrong second
            # link is worse than no second link.
            return {'url': url, 'title': best['title'], 'kind': cls['kind'],
                    'is_live': cls['is_live'],
                    'is_official': cls['is_official'],
                    'clean_song': clean_song}

        fallback = (f"https://www.youtube.com/results?search_query="
                    f"{quote(f'{artist} {song}'.strip())}")
        return {'url': fallback, 'title': '', 'kind': 'none',
                'is_live': False, 'is_official': False,
                'clean_song': clean_song}

    except Exception as e:
        logger.error(f"Error getting YouTube link: {e}")
        return {'url': f"https://www.youtube.com/results?search_query="
                       f"{quote(f'{artist} {song}')}",
                'title': '', 'kind': 'none',
                'is_live': False, 'is_official': False,
                'clean_song': _clean_song_title(song)}


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
        # The resolved song title may carry the live recording's qualifier
        # ("Uninvited - Live at Newport Folk"); show the clean song title.
        clean = info.get('clean_song') or song
        live_title = f"{artist} — {clean}" if clean else artist
        live_ref = f"{artist} - {clean}" if clean else artist
        return (
            f"🎬 {live_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎥 Live version — no official video found:\n"
            f"▶️ Watch now:\n{url}\n\n"
            f"🎤 /lyrics {live_ref}\n"
            f"📊 /analyze {live_ref}"
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
