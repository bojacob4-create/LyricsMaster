"""Round-41: /playlist — build an artist playlist blending three live slices.

Slices (no Spotify involved — everything comes from sources the bot
already talks to):
  all-time  — Last.fm artist.getTopTracks (all-time playcounts)
  new       — iTunes Search, newest releaseDate first (<= NEW_SONG_YEARS old)
  trending  — the artist's entries in the live US Apple Music Top 100

General by design: works for any artist iTunes/Last.fm know, not just
the one it was prototyped with. Slice quotas split the requested count
into thirds (remainder -> all-time, then new, then trending); shortfalls
rebalance from the other slices and the output says so honestly.
"""

import datetime
import logging
import os
import re
from itertools import zip_longest

import requests

from services.artist_service import _get_cached_chart
from services.youtube_service import _clean_song_title

logger = logging.getLogger(__name__)

PLAYLIST_DEFAULT_COUNT = 12
PLAYLIST_MAX_COUNT = 15
NEW_SONG_YEARS = 2  # "new" = released within the last N years

NOTE_TRENDING = '🔥 Trending now'
NOTE_NEW = '🆕 New release'
NOTE_ALL_TIME = '⭐ All-time favorite'

_ITUNES_SEARCH_URL = 'https://itunes.apple.com/search'
_LASTFM_URL = 'https://ws.audioscrobbler.com/2.0/'


# ── argument parsing ──────────────────────────────────────────────────────
def parse_playlist_args(args):
    """Parse /playlist args -> (artist, count, capped, full_fallback).

    The trailing token is a count when it is all digits and at least one
    other token exists. 100 -> capped to PLAYLIST_MAX_COUNT. A trailing
    number that is really part of the artist name ("Blink 182") is
    recovered via full_fallback: the caller retries with the whole string
    when the stripped artist yields nothing.
    """
    toks = [t for t in (args or []) if str(t).strip()]
    count = PLAYLIST_DEFAULT_COUNT
    capped = False
    number = None
    rest = list(toks)
    if len(rest) >= 2 and re.fullmatch(r'\d+', rest[-1] or ''):
        number = rest[-1]
        rest = rest[:-1]
        n = int(number)
        if n >= 1:
            if n > PLAYLIST_MAX_COUNT:
                count, capped = PLAYLIST_MAX_COUNT, True
            else:
                count = n
        # n == 0 (or absurd) -> default count
    artist = ' '.join(rest).strip()
    full_fallback = f"{artist} {number}".strip() if number else None
    return artist, count, capped, full_fallback


def _quotas(n):
    """Split n into (all_time, new, trending); remainder -> all-time first."""
    base, rem = divmod(max(int(n), 0), 3)
    q = [base, base, base]
    for i in range(rem):
        q[i] += 1
    return tuple(q)


# ── slice fetchers (each [] on any miss, never raises) ─────────────────────
def _artist_words_match(query, candidate):
    ql = (query or '').strip().lower()
    qw = set(ql.split())
    cl = (candidate or '').lower()
    cw = set(cl.replace(',', ' ').replace('&', ' ').split())
    return bool(ql) and (ql in cl or qw <= cw)


def _tidy_caps(title):
    """iTunes lists some tracks in ALL CAPS ("RIGHT NOW", "I DON'T CARE").

    Tidy those to normal case; leave everything else untouched. The regex
    keeps apostrophes inside words ("Don't", not "Don'T").
    """
    t = (title or '').strip()
    if t and t == t.upper() and t != t.lower():
        return re.sub(r"[A-Za-z]+('[A-Za-z]+)?",
                      lambda m: m.group(0).capitalize(), t)
    return t


def _dedup_key(title):
    """Dedup key: recording qualifiers stripped, then lowercased.

    'Stan (Live At Wembley 2014)' and 'Stan' are the same song — the
    round-28 cleaner strips the live qualifier so cross-slice duplicates
    can't slip through exact-match dedup. Display titles are untouched;
    only the key is normalized.
    """
    return _clean_song_title(title).lower().strip()


def _qualifier_segments(title):
    """The qualifier parts of a title: parentheticals, brackets, ' - ' tails.

    Only these segments are ever judged for variant/junk markers — the bare
    title is never flagged, so "Live Your Life" and "Cover Me" stay safe.
    """
    t = title or ''
    segs = re.findall(r'\([^)]*\)', t) + re.findall(r'\[[^\]]*\]', t)
    parts = t.split(' - ')
    if len(parts) > 1:
        segs.append(' - '.join(parts[1:]))
    return ' '.join(segs).lower()


# Qualifier markers that demote a "new" pick to fallback: the recording is
# genuinely the artist's, but it is not the canonical studio song.
_SOFT_VARIANT_RES = [
    r'\blive\b', r'\bunplugged\b', r'\bacoustic\b', r'\bconcert\b',
    r'\btour\b', r'\bfestival\b', r'\bsession\b', r'\bnpr\b',
    r'\btiny desk\b', r'\bremix\b', r'\bremaster(?:ed)?\b', r'\bcover\b',
]

# Qualifier fragments that are never the artist's recording at all —
# karaoke/tribute/8D/sped-up fare (cf. _JUNK_TITLE_BITS in
# discovery_service, which guards the mood mixes the same way).
_JUNK_VARIANT_BITS = ('karaoke', 'tribute', '8d audio', '8d', 'slowed',
                     'sped up', 'nightcore', '1 hour', '10 hours',
                     'sing along', 'sax solo', 'reverb version')


def _is_soft_variant(title):
    """A live/cover/remix/remaster qualifier: real recording, not canonical."""
    quals = _qualifier_segments(title)
    return any(re.search(p, quals) for p in _SOFT_VARIANT_RES)


def _is_junk_variant(title):
    """Karaoke/tribute/8D-style qualifier: not the artist's recording."""
    quals = _qualifier_segments(title)
    return any(b in quals for b in _JUNK_VARIANT_BITS)


def _lastfm_all_time(artist, limit):
    """All-time most-played tracks for the artist. [title, ...]."""
    try:
        api_key = os.environ.get('LASTFM_API_KEY', '')
        if not api_key or not artist:
            return []
        resp = requests.get(
            _LASTFM_URL,
            params={'method': 'artist.getTopTracks', 'artist': artist,
                    'api_key': api_key, 'format': 'json',
                    'limit': max(int(limit), 1)},
            timeout=6,
        )
        if resp.status_code != 200:
            return []
        tracks = resp.json().get('toptracks', {}).get('track', [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        names = [t.get('name', '').strip() for t in tracks
                 if t.get('name', '').strip()]
        return list(dict.fromkeys(names))[:limit]
    except Exception as e:
        logger.debug(f"playlist Last.fm miss for '{artist}': {e}")
        return []


def _itunes_new_songs(artist, limit):
    """Newest tracks by releaseDate within NEW_SONG_YEARS.

    Returns (canonical_artist, [(title, release_date), ...]) newest-first.
    canonical_artist is the most common artistName among matches, so
    "tyla" displays as "Tyla".
    """
    try:
        if not artist:
            return None, []
        resp = requests.get(
            _ITUNES_SEARCH_URL,
            params={'term': artist, 'media': 'music', 'entity': 'song',
                    'attribute': 'artistTerm', 'limit': 100},
            timeout=6,
        )
        if resp.status_code != 200:
            return None, []
        cutoff = (datetime.date.today()
                  - datetime.timedelta(days=365 * NEW_SONG_YEARS)).isoformat()
        seen, picks, name_votes = set(), [], {}
        for r in resp.json().get('results', []):
            aname = (r.get('artistName') or '').strip()
            tname = (r.get('trackName') or '').strip()
            if not tname or not _artist_words_match(artist, aname):
                continue
            name_votes[aname] = name_votes.get(aname, 0) + 1
            date = (r.get('releaseDate') or '')[:10]
            key = tname.lower()
            if not date or date < cutoff or key in seen:
                continue
            seen.add(key)
            picks.append((tname, date))
        picks.sort(key=lambda p: p[1], reverse=True)
        # Prefer canonical studio recordings: demote live/cover/remix
        # variants to the back of the line, drop karaoke/tribute junk
        # outright. A real variant still beats an empty slice, so it stays
        # as fallback rather than being skipped.
        clean, variants = [], []
        for t, d in picks:
            if _is_junk_variant(t):
                continue
            (variants if _is_soft_variant(t) else clean).append((t, d))
        canonical = max(name_votes, key=name_votes.get) if name_votes else None
        return canonical, (clean + variants)[:limit]
    except Exception as e:
        logger.debug(f"playlist iTunes miss for '{artist}': {e}")
        return None, []


def _chart_trending(artist, limit):
    """The artist's songs in the live US Apple Top 100, chart order."""
    try:
        raw = _get_cached_chart('us')
        if not raw or not artist:
            return []
        out, seen = [], set()
        for item in raw:
            if not _artist_words_match(artist, item.get('artist', '')):
                continue
            song = (item.get('song') or '').strip()
            key = song.lower()
            if not song or key in seen:
                continue
            seen.add(key)
            out.append(song)
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        logger.debug(f"playlist chart miss for '{artist}': {e}")
        return []


# ── assembly ──────────────────────────────────────────────────────────────
def build_artist_playlist(artist_query, count):
    """Build the mixed playlist.

    Returns (canonical_artist, songs, meta) where songs are
    [{'artist', 'song', 'note'}] interleaved trending -> all-time -> new,
    and meta carries {'rebalanced': bool, 'short': {slice: missing}}.
    songs == [] means the artist resolved to nothing.
    """
    artist = (artist_query or '').strip()
    if not artist:
        return artist, [], {'rebalanced': False, 'short': {}}

    q_all, q_new, q_tr = _quotas(count)
    headroom = 8

    all_time = _lastfm_all_time(artist, q_all + headroom)
    canonical, new_pairs = _itunes_new_songs(artist, q_new + headroom)
    display = canonical or artist
    trending = _chart_trending(display, q_tr + headroom)

    slices = {'all_time': [], 'new': [], 'trending': []}
    seen = set()

    def claim(names, note, quota):
        out = []
        for nm in names:
            if len(out) >= quota:
                break
            key = _dedup_key(nm)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({'artist': display, 'song': _tidy_caps(nm),
                        'note': note})
        return out

    slices['all_time'] = claim(all_time, NOTE_ALL_TIME, q_all)
    slices['new'] = claim([t for t, _ in new_pairs], NOTE_NEW, q_new)
    slices['trending'] = claim(trending, NOTE_TRENDING, q_tr)

    # Rebalance: fill shortfalls from leftover pools, most reliable first.
    quotas = {'all_time': q_all, 'new': q_new, 'trending': q_tr}
    leftovers = []
    for pool_names, note in ((all_time, NOTE_ALL_TIME),
                             (trending, NOTE_TRENDING),
                             ([t for t, _ in new_pairs], NOTE_NEW)):
        for nm in pool_names:
            key = _dedup_key(nm)
            if key and key not in seen:
                seen.add(key)
                leftovers.append({'artist': display,
                                  'song': _tidy_caps(nm), 'note': note})

    short = {}
    li = 0
    for key in ('new', 'trending', 'all_time'):
        missing = quotas[key] - len(slices[key])
        if missing <= 0:
            continue
        while missing > 0 and li < len(leftovers):
            slices[key].append(leftovers[li])
            li += 1
            missing -= 1
        if missing > 0:
            short[key] = missing

    # Interleave so the list feels like a real mix: trending opens,
    # then all-time, then new — the way the prototype list was sequenced.
    songs = [s for group in zip_longest(slices['trending'],
                                        slices['all_time'],
                                        slices['new'])
             for s in group if s]

    meta = {'rebalanced': bool(short) or li > 0, 'short': short}
    return display, songs, meta


# ── formatting ────────────────────────────────────────────────────────────
def format_playlist(artist, songs, capped=False, meta=None):
    """Render the playlist message. Every song carries its slice note."""
    meta = meta or {}
    lines = [f"🎧 {artist} — Your Playlist", "━━━━━━━━━━━━━━━━━━━━━", ""]
    if capped:
        lines.append(f"📏 {PLAYLIST_MAX_COUNT} is the max that works in "
                     "chat — here's your 15.\n")
    short = meta.get('short') or {}
    if short:
        bits = []
        if short.get('new'):
            bits.append("new releases")
        if short.get('trending'):
            bits.append("charting songs")
        if short.get('all_time'):
            bits.append("all-time favorites")
        lines.append("ℹ️ Fewer {} found than the mix called for — "
                     "filled the rest from the other slices.\n"
                     .format(' and '.join(bits)))
    for i, s in enumerate(songs, 1):
        lines.append(f"{i}. {s['song']}")
        lines.append(f"   ↳ {s['note']}")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎵 Tap a song below to explore:")
    return '\n'.join(lines).rstrip()
