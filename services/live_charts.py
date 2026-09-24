"""Live chart provider for the Lyrics Master bot.

Replaces the old static song pools (RANDOM_SONGS_POOL, quiz pool, curated
recommendation pools) with live, regularly-refreshed chart data:

  - Apple Music Top 100 (US) — global chart + per-genre filtering
  - Last.fm chart.getTopTracks — what's being played right now worldwide

Design rules:
  - Chart fetches are cached (in-memory + a small disk JSON cache, ~6h TTL)
    so commands stay fast and a dead feed doesn't kill a command.
  - Every public function NEVER raises: on any failure it returns [] (or the
    last cached data), and callers decide how to degrade gracefully.
  - Module import performs NO network I/O.

Cache file: <repo>/live_charts_cache.json  (repo root, not committed secrets)
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_CHART_TTL = 6 * 3600  # refresh charts at most every 6 hours
_LASTFM_TTL = 6 * 3600

_APPLE_URL = ("https://rss.applemarketingtools.com/api/v2/us/music/"
              "most-played/100/songs.json")
_ITUNES_FALLBACK_URL = "https://itunes.apple.com/us/rss/topsongs/limit=100/json"
_LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"

_HEADERS = {'User-Agent': 'LyricsMasterBot/1.0'}

_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'live_charts_cache.json')

# Our genre keys -> Apple Music genre names (as they appear in the chart feed).
_GENRE_TO_APPLE = {
    'pop': 'Pop',
    'rap': 'Hip-Hop/Rap',
    'rnb': 'R&B/Soul',
    'rock': 'Alternative',
    'country': 'Country',
    'latin': 'Latin',
    'kpop': 'K-Pop',
    'soul': 'R&B/Soul',
    'dance': 'Dance',
    'electronic': 'Dance',
}

# In-memory caches: full chart entries = {artist, song, genres}
_mem = {'chart': None, 'chart_ts': 0.0,
        'lastfm': None, 'lastfm_ts': 0.0}


# ── Disk cache ────────────────────────────────────────────────────────────────

def _load_disk_cache() -> Optional[List[Dict]]:
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('fetched_at', 0) > _CHART_TTL:
            return None
        chart = data.get('chart')
        if chart and len(chart) >= 10:
            logger.info(f"[CHARTS] Loaded {len(chart)} songs from disk cache")
            return chart
    except Exception as e:
        logger.debug(f"[CHARTS] Disk cache read failed: {e}")
    return None


def _save_disk_cache(chart: List[Dict]) -> None:
    try:
        tmp = _CACHE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'fetched_at': time.time(), 'chart': chart}, f)
        os.replace(tmp, _CACHE_FILE)
    except Exception as e:
        logger.debug(f"[CHARTS] Disk cache write failed: {e}")


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _parse_apple_marketing(data: Dict) -> List[Dict]:
    items = data.get('feed', {}).get('results', [])
    songs = []
    for item in items:
        name = (item.get('name') or '').strip()
        artist = (item.get('artistName') or '').strip()
        if not name or not artist:
            continue
        genres = [g.get('name', '') for g in item.get('genres', [])
                  if g.get('name') and g.get('name') != 'Music']
        songs.append({'artist': artist, 'song': name, 'genres': genres})
    return songs


def _label(entry: Dict, key: str) -> str:
    val = entry.get(key)
    if isinstance(val, dict):
        return (val.get('label') or '').strip()
    return (val or '').strip()


def _parse_itunes_rss(data: Dict) -> List[Dict]:
    entries = data.get('feed', {}).get('entry', [])
    songs = []
    for entry in entries:
        name = _label(entry, 'im:name')
        artist = _label(entry, 'im:artist')
        if not name or not artist:
            continue
        genre = ''
        cat = entry.get('category', {})
        if isinstance(cat, dict):
            genre = ((cat.get('attributes') or {}).get('term') or '').strip()
        songs.append({'artist': artist, 'song': name,
                      'genres': [genre] if genre else []})
    return songs


def _fetch_apple_chart() -> List[Dict]:
    """Fetch the Apple Music Top 100 (US). Primary + fallback feed."""
    # Primary: applemarketingtools (proven in prod, carries genre tags)
    try:
        r = requests.get(_APPLE_URL, timeout=10, headers=_HEADERS)
        if r.status_code == 200:
            songs = _parse_apple_marketing(r.json())
            if len(songs) >= 10:
                logger.info(f"[CHARTS] Apple chart: {len(songs)} songs (primary)")
                return songs
    except Exception as e:
        logger.debug(f"[CHARTS] Primary Apple feed failed: {e}")

    # Fallback: classic iTunes RSS feed
    try:
        r = requests.get(_ITUNES_FALLBACK_URL, timeout=10, headers=_HEADERS)
        if r.status_code == 200:
            songs = _parse_itunes_rss(r.json())
            if len(songs) >= 10:
                logger.info(f"[CHARTS] Apple chart: {len(songs)} songs (fallback feed)")
                return songs
    except Exception as e:
        logger.debug(f"[CHARTS] Fallback iTunes feed failed: {e}")

    return []


def _get_chart_entries() -> List[Dict]:
    """Full cached chart entries (with genre tags). Never raises."""
    try:
        now = time.time()
        if _mem['chart'] and (now - _mem['chart_ts']) < _CHART_TTL:
            return _mem['chart']

        chart = _fetch_apple_chart()
        if chart:
            _mem['chart'] = chart
            _mem['chart_ts'] = now
            _save_disk_cache(chart)
            return chart

        # Fetch failed — fall back to disk cache even if stale
        if _mem['chart']:
            return _mem['chart']
        disk = _load_disk_cache()
        if disk:
            _mem['chart'] = disk
            _mem['chart_ts'] = now - _CHART_TTL + 300  # retry soon
            return disk
        return []
    except Exception as e:
        logger.error(f"[CHARTS] Unexpected chart error: {e}")
        return _mem.get('chart') or []


# ── Public API ────────────────────────────────────────────────────────────────

def get_top_songs(limit: int = 100) -> List[Dict]:
    """Live Apple Music Top 100 (US), cached ~6h.

    Returns [{artist, song}, ...].  [] when the feed AND every cache miss.
    """
    return [{'artist': s['artist'], 'song': s['song']}
            for s in _get_chart_entries()[:limit]]


def get_top_by_genre(genre_key: str, limit: int = 20) -> List[Dict]:
    """Live genre slice of the Apple chart, e.g. 'pop', 'rap', 'rock'.

    Returns [] for unknown genres or when fewer than 3 songs match — callers
    should fall back to get_top_songs() rather than a static pool.
    """
    try:
        apple_genre = _GENRE_TO_APPLE.get((genre_key or '').lower().strip())
        if not apple_genre:
            return []
        out, seen = [], set()
        for s in _get_chart_entries():
            if apple_genre in s.get('genres', []):
                key = s['artist'].lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({'artist': s['artist'], 'song': s['song']})
                if len(out) >= limit:
                    break
        return out if len(out) >= 3 else []
    except Exception as e:
        logger.error(f"[CHARTS] genre filter error: {e}")
        return []


def get_lastfm_chart(limit: int = 50) -> List[Dict]:
    """Last.fm chart.getTopTracks — what's hot worldwide right now.

    In-memory cached ~6h. [] when the key is missing or the call fails.
    """
    try:
        now = time.time()
        if _mem['lastfm'] and (now - _mem['lastfm_ts']) < _LASTFM_TTL:
            return _mem['lastfm'][:limit]

        api_key = os.environ.get('LASTFM_API_KEY', '')
        if not api_key:
            return []

        r = requests.get(
            _LASTFM_URL,
            params={'method': 'chart.getTopTracks', 'api_key': api_key,
                    'format': 'json', 'limit': max(limit, 30)},
            timeout=8)
        tracks = r.json().get('tracks', {}).get('track', [])
        out = []
        for t in tracks:
            try:
                a = (t.get('artist', {}).get('name') or '').strip()
                n = (t.get('name') or '').strip()
                if a and n:
                    out.append({'artist': a, 'song': n})
            except (AttributeError, TypeError):
                continue
        if out:
            _mem['lastfm'] = out
            _mem['lastfm_ts'] = now
            logger.info(f"[CHARTS] Last.fm chart: {len(out)} tracks")
        return out[:limit]
    except Exception as e:
        logger.debug(f"[CHARTS] Last.fm chart failed: {e}")
        return _mem.get('lastfm') or []
