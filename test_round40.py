"""Round 40: /top is 100% live for all genres (10 after round-84 added dance).

- Per-genre home Apple charts (kpop -> Korea, afrobeats -> Nigeria, rest -> US)
- Last.fm tag tracks fill thin Apple slices (still live, labeled)
- Static GENRE_TOP_SONGS pool is NEVER served by /top
- Honest "charts unreachable" instead of stale picks
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load the bot's own env for the Last.fm key (live smoke test only).
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
if os.path.exists(_env):
    for _line in open(_env):
        if _line.startswith('LASTFM_API_KEY='):
            os.environ.setdefault('LASTFM_API_KEY',
                                  _line.strip().split('=', 1)[1])

from services import artist_service as AS

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _apple_item(artist, song, genres):
    return {'artist': artist, 'song': song, 'genres': genres}


# ── genre resolution ──────────────────────────────────────────────────────
check("resolve pop", AS.resolve_genre_key('pop') == 'pop')
check("resolve alias hip-hop -> rap", AS.resolve_genre_key('hip-hop') == 'rap')
check("resolve alias k-pop -> kpop", AS.resolve_genre_key('k-pop') == 'kpop')
check("resolve alias r&b -> rnb", AS.resolve_genre_key('r&b') == 'rnb')
check("resolve case-insensitive", AS.resolve_genre_key('KPop') == 'kpop')
check("resolve unknown -> None", AS.resolve_genre_key('polka') is None)
check("resolve empty -> None", AS.resolve_genre_key('') is None)

# ── genre registry ────────────────────────────────────────────────────────
genres = AS.get_available_genres()
check("10 genres (round-84 added dance)", len(genres) == 10)
for _g in ['afrobeats', 'pop', 'rap', 'rnb', 'rock', 'latin', 'country',
           'soul', 'kpop', 'dance']:
    check(f"genre present: {_g}", _g in genres)

# ── home-chart mapping ────────────────────────────────────────────────────
check("kpop -> Korea chart", AS.APPLE_GENRE_MAP['kpop'][0] == 'kr')
check("afrobeats -> Nigeria chart", AS.APPLE_GENRE_MAP['afrobeats'][0] == 'ng')
check("pop -> US chart", AS.APPLE_GENRE_MAP['pop'][0] == 'us')
check("kpop tag is K-Pop", AS.APPLE_GENRE_MAP['kpop'][1] == 'K-Pop')
check("afrobeats tag is Afrobeats",
      AS.APPLE_GENRE_MAP['afrobeats'][1] == 'Afrobeats')
check("rock matches Rock + Alternative",
      set(AS.APPLE_GENRE_MAP['rock'][1]) == {'Rock', 'Alternative'})

# ── _get_live_genre_songs with mocked sources ─────────────────────────────
_orig_chart = AS._get_cached_chart
_orig_lfm = AS._get_lastfm_genre_songs


def _mock_chart_factory(items):
    def _fake(country='us'):
        return items
    return _fake


try:
    # 1) Full Apple slice: 7 Apple songs, Last.fm never consulted.
    apple7 = [_apple_item(f'Artist{i}', f'Song{i}', ['K-Pop'])
              for i in range(7)]
    AS._get_cached_chart = _mock_chart_factory(apple7)
    lfm_called = []
    AS._get_lastfm_genre_songs = lambda *a, **k: lfm_called.append(1) or []
    songs = AS._get_live_genre_songs('kpop')
    check("apple-full: 7 songs", songs is not None and len(songs) == 7)
    check("apple-full: all Charting now on Apple Music",
          all(s['note'] == 'Charting now on Apple Music' for s in songs))
    check("apple-full: last.fm not consulted", lfm_called == [])

    # 2) Thin slice: 2 Apple + 5 Last.fm, deduped, provenance labeled.
    apple2 = [_apple_item('A1', 'S1', ['Latin']), _apple_item('A2', 'S2', ['Latin'])]
    AS._get_cached_chart = _mock_chart_factory(apple2)
    AS._get_lastfm_genre_songs = lambda g, exclude_artists=frozenset(), \
        exclude_songs=frozenset(), limit=7: [
            {'artist': f'LFM{i}', 'song': f'LS{i}', 'note': 'Trending on Last.fm'}
            for i in range(5)]
    songs = AS._get_live_genre_songs('latin')
    check("thin: blended to 7", songs is not None and len(songs) == 7)
    check("thin: 2 apple + 5 lastfm",
          sum(s['note'] == 'Charting now on Apple Music' for s in songs) == 2
          and sum(s['note'] == 'Trending on Last.fm' for s in songs) == 5)
    check("thin: apple songs come first",
          songs[0]['note'] == 'Charting now on Apple Music'
          and songs[2]['note'] == 'Trending on Last.fm')

    # 3) Apple down, Last.fm up: pure Last.fm card.
    AS._get_cached_chart = _mock_chart_factory(None)
    AS._get_lastfm_genre_songs = lambda g, exclude_artists=frozenset(), \
        exclude_songs=frozenset(), limit=7: [
            {'artist': f'L{i}', 'song': f'M{i}', 'note': 'Trending on Last.fm'}
            for i in range(4)]
    songs = AS._get_live_genre_songs('pop')
    check("apple-down: last.fm only",
          songs is not None and len(songs) == 4
          and all(s['note'] == 'Trending on Last.fm' for s in songs))

    # 4) Everything down: None (no static fallback).
    AS._get_cached_chart = _mock_chart_factory(None)
    AS._get_lastfm_genre_songs = lambda *a, **k: []
    check("all-down: None", AS._get_live_genre_songs('pop') is None)

    # 5) Unknown genre key: None.
    check("unknown key: None", AS._get_live_genre_songs('polka') is None)

    # 6) Dedup: Last.fm dup of an Apple artist is skipped (mock the fetch
    # layer so the REAL _get_lastfm_genre_songs does the dedup).
    apple1 = [_apple_item('Dua Lipa', 'Levitating', ['Pop'])]
    AS._get_cached_chart = _mock_chart_factory(apple1)
    _orig_fetch = AS._fetch_lastfm_tag_tracks
    AS._fetch_lastfm_tag_tracks = lambda tag, limit=25: [
        {'artist': 'DUA LIPA', 'song': 'Other'},
        {'artist': 'New Act', 'song': 'Hit'}]
    AS._get_lastfm_genre_songs = _orig_lfm
    AS._genre_tag_cache.clear()
    songs = AS._get_live_genre_songs('pop')
    AS._fetch_lastfm_tag_tracks = _orig_fetch
    artists = [s['artist'].lower() for s in songs]
    check("dedup: no repeated artist", len(artists) == len(set(artists)))
    check("dedup: dup artist skipped, other kept",
          artists == ['dua lipa', 'new act'])
finally:
    AS._get_cached_chart = _orig_chart
    AS._get_lastfm_genre_songs = _orig_lfm

# ── get_top_by_genre: static pool never served ────────────────────────────
check("unknown genre -> None", AS.get_top_by_genre('polka') is None)
_orig_live = AS._get_live_genre_songs
try:
    AS._get_live_genre_songs = lambda g: None
    check("live down -> None (NOT static pool)",
          AS.get_top_by_genre('pop') is None)
    AS._get_live_genre_songs = lambda g: [{'artist': 'X', 'song': 'Y',
                                           'note': 'Charting now on Apple Music'}]
    res = AS.get_top_by_genre('k-pop')
    check("alias resolves + live tuple", res is not None and res[0] == 'kpop')
finally:
    AS._get_live_genre_songs = _orig_live

# ── format_top_songs source labeling ──────────────────────────────────────
def _card(songs):
    return AS.format_top_songs('kpop', songs)


_apple = [{'artist': 'A', 'song': 'S', 'note': 'Charting now on Apple Music'}]
_lfm = [{'artist': 'A', 'song': 'S', 'note': 'Popular on Last.fm'}]
check("source line: apple only",
      "Source: Apple Music Charts" in _card(_apple))
check("source line: last.fm only", "Source: Last.fm" in _card(_lfm))
check("source line: blended",
      "Sources: Apple Music Charts + Last.fm" in _card(_apple + _lfm))
check("per-song note: only the differing note renders (1-1 tie -> first-seen wins)",
      "↳ Charting now on Apple Music" not in _card(_apple + _lfm)
      and "↳ Popular on Last.fm" in _card(_apple + _lfm))
check("per-song notes: all-same source renders zero sub-lines",
      "↳" not in _card(_apple))

# ── live smoke test (real network; skips cleanly if charts unreachable) ───
for _g in ['kpop', 'afrobeats', 'latin', 'pop']:
    try:
        _res = AS.get_top_by_genre(_g)
    except Exception as _e:
        print(f"SKIP (network): live smoke {_g}: {_e}")
        continue
    if _res is None:
        print(f"SKIP (charts unreachable): live smoke {_g}")
        continue
    _genre, _songs = _res
    _live_notes = ('Charting now on Apple Music', 'Popular on Last.fm')
    check(f"live smoke {_g}: all songs live",
          len(_songs) > 0 and all(s.get('note') in _live_notes for s in _songs))
    if _g in ('kpop', 'afrobeats'):
        check(f"live smoke {_g}: served by home chart",
              any(s['note'] == 'Charting now on Apple Music' for s in _songs))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
