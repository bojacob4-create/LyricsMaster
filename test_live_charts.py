"""Live-chart tests — no Telegram network, no real HTTP.

Covers the "bot = live" migration:
  1. live_charts parsing (primary + fallback feeds), caching, failure paths
  2. get_random_song / get_quiz_songs draw from the live chart (mocked)
  3. similar-songs pipeline uses only live sources (no curated pool)

Run: ../venv/bin/python test_live_charts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"[FAIL] {name} {detail}")


from services import live_charts as lc
from services.artist_service import get_random_song
from services import quiz_service as qs

# ── Fixtures ────────────────────────────────────────────────────────────────

def _mk(genre_label, apple_genre, n=4):
    return [{'artist': f'{genre_label} Artist {i}', 'song': f'{genre_label} Hit {i}',
             'genres': [apple_genre]} for i in range(1, n + 1)]


FIXTURE_CHART = (
    _mk('Pop', 'Pop')
    + _mk('Rap', 'Hip-Hop/Rap')
    + _mk('Rock', 'Alternative')
    + _mk('Country', 'Country')
    + _mk('Rnb', 'R&B/Soul')
    + _mk('Kpop', 'K-Pop')
)


def _reset_mem():
    lc._mem['chart'] = None
    lc._mem['chart_ts'] = 0.0
    lc._mem['lastfm'] = None
    lc._mem['lastfm_ts'] = 0.0


# ── 1. Apple primary-feed parsing ───────────────────────────────────────────

print("== primary feed parsing ==")
_apple_json = {
    'feed': {'results': [
        {'name': 'Song A', 'artistName': 'Artist A',
         'genres': [{'name': 'Pop'}, {'name': 'Music'}]},
        {'name': '', 'artistName': 'No Name'},          # skipped
        {'name': 'Song B', 'artistName': 'Artist B',
         'genres': [{'name': 'Hip-Hop/Rap'}]},
    ]}
}
parsed = lc._parse_apple_marketing(_apple_json)
check("primary parser: 2 valid songs", len(parsed) == 2, repr(parsed))
check("primary parser: genres strip 'Music'",
      parsed[0]['genres'] == ['Pop'], repr(parsed[0]))

# ── 2. iTunes fallback-feed parsing ─────────────────────────────────────────

print("== fallback feed parsing ==")
_itunes_json = {
    'feed': {'entry': [
        {'im:name': {'label': 'Fall Song'}, 'im:artist': {'label': 'Fall Artist'},
         'category': {'attributes': {'term': 'Pop'}}},
        {'im:name': {'label': 'No Artist'}, 'im:artist': {'label': ''}},
    ]}
}
parsed2 = lc._parse_itunes_rss(_itunes_json)
check("fallback parser: 1 valid song", len(parsed2) == 1, repr(parsed2))
check("fallback parser: genre captured", parsed2[0]['genres'] == ['Pop'])

# ── 3. get_top_songs with mocked fetcher ────────────────────────────────────

print("== get_top_songs (mocked fetch) ==")
_reset_mem()
lc._fetch_apple_chart = lambda: list(FIXTURE_CHART)
top = lc.get_top_songs()
check("top songs returns fixture", len(top) == 24 and top[0]['song'] == 'Pop Hit 1')
check("top songs shape is {artist, song, release_date}",
      set(top[0].keys()) == {'artist', 'song', 'release_date'}, repr(top[0]))
top3 = lc.get_top_songs(limit=3)
check("limit respected", len(top3) == 3)

# ── 4. Genre filtering ──────────────────────────────────────────────────────

print("== get_top_by_genre ==")
check("pop genre", [s['song'] for s in lc.get_top_by_genre('pop')] == [f'Pop Hit {i}' for i in range(1,5)])
check("rap genre", [s['song'] for s in lc.get_top_by_genre('rap')] == [f'Rap Hit {i}' for i in range(1,5)])
check("rock genre", [s['song'] for s in lc.get_top_by_genre('rock')] == [f'Rock Hit {i}' for i in range(1,5)])
check("unknown genre -> []", lc.get_top_by_genre('zydeco') == [])
check("kpop genre", [s['song'] for s in lc.get_top_by_genre('kpop')] == [f'Kpop Hit {i}' for i in range(1,5)])
check("thin genre slice (<3) -> []", lc.get_top_by_genre('dance') == [])

# ── 5. Total failure -> [] (never raises) ───────────────────────────────────

print("== total failure paths ==")
_reset_mem()
lc._fetch_apple_chart = lambda: []
_cache_bak = None
if os.path.exists(lc._CACHE_FILE):
    _cache_bak = lc._CACHE_FILE + '.testbak'
    os.rename(lc._CACHE_FILE, _cache_bak)
try:
    check("get_top_songs -> [] on total failure", lc.get_top_songs() == [])
    check("get_top_by_genre -> [] on total failure",
          lc.get_top_by_genre('pop') == [])
    check("get_random_song -> None on total failure",
          get_random_song(user_id=4242) is None)
    check("get_quiz_songs -> [] on total failure", qs.get_quiz_songs() == [])
finally:
    if _cache_bak and os.path.exists(_cache_bak):
        os.rename(_cache_bak, lc._CACHE_FILE)

# ── 6. Last.fm chart without key -> [] (never raises) ───────────────────────

print("== lastfm chart without key ==")
old_key = os.environ.pop('LASTFM_API_KEY', None)
_reset_mem()
check("get_lastfm_chart -> [] without key", lc.get_lastfm_chart() == [])
if old_key is not None:
    os.environ['LASTFM_API_KEY'] = old_key

# ── 7. get_random_song draws from live chart ────────────────────────────────

print("== get_random_song live ==")
_reset_mem()
lc._fetch_apple_chart = lambda: list(FIXTURE_CHART)
from services.artist_service import _recent_random_picks
_recent_random_picks.pop(777, None)
picks = {get_random_song(user_id=777)['song'] for _ in range(30)}
check("picks come from the live chart",
      picks <= {s['song'] for s in FIXTURE_CHART}, repr(picks))
pg = get_random_song(user_id=778, genre='pop')
check("genre pick is a pop chart song", pg and pg['song'].startswith('Pop Hit'), repr(pg))
rg = get_random_song(user_id=778, genre='rap')
check("genre pick is a rap chart song", rg and rg['song'].startswith('Rap Hit'), repr(rg))
# unknown genre falls back to global chart (still live, no crash)
ug = get_random_song(user_id=778, genre='zydeco')
check("unknown genre falls back to global chart", bool(ug), repr(ug))

# no-repeat window: 12 distinct picks, then repeats allowed but de-duped
_recent_random_picks.pop(779, None)
seq = [get_random_song(user_id=779)['song'] for _ in range(12)]
check("12 consecutive picks are distinct", len(set(seq)) == 12, repr(seq))

# ── 8. get_quiz_songs draws from live chart ─────────────────────────────────

print("== get_quiz_songs live ==")
_reset_mem()
lc._fetch_apple_chart = lambda: list(FIXTURE_CHART)
qz = qs.get_quiz_songs()
check("quiz songs come from live chart",
      len(qz) == 24 and qz[0]['song'] == 'Pop Hit 1', repr(qz[:2]))

# ── 9. Similar-songs pipeline: live sources only, no curated fallback ──────

print("== similar songs: live-only pipeline ==")
import services.recommendation_service as rec

# All three live sources empty -> [] (the old curated fallback is gone)
rec._get_lastfm_recommendations = lambda *a, **k: []
rec._fetch_apple_top_songs = lambda: []
lc.get_lastfm_chart = lambda limit=50: []
merged = rec._get_similar_songs_uncached('Adele', 'Hello', 'sad')
check("all sources empty -> [] (no curated fallback)", merged == [],
      repr(merged))

# Only the Last.fm chart alive -> chart-only recs, quality-gated.
# (Real pop artists so the vibe/ecosystem gates have something to chew on.)
_reset_mem()
lc.get_lastfm_chart = lambda limit=50: [
    {'artist': 'Sabrina Carpenter', 'song': 'Espresso'},
    {'artist': 'Chappell Roan', 'song': 'Good Luck, Babe!'},
    {'artist': 'Olivia Rodrigo', 'song': 'vampire'},
    {'artist': 'Dua Lipa', 'song': 'Houdini'},
    {'artist': 'Ariana Grande', 'song': "we can't be friends"},
    {'artist': 'Billie Eilish', 'song': 'Birds of a Feather'},
]
prof = rec._build_song_profile(
    'Taylor Swift', 'Cruel Summer', 'happy',
    rec._detect_genre('Taylor Swift', 'Cruel Summer', 'happy'))
chart_recs = rec._get_lastfm_chart_recommendations(
    'Taylor Swift', 'Cruel Summer', prof)
check("chart source returns scored recs",
      chart_recs is not None and len(chart_recs) >= 3,
      repr(chart_recs))
check("chart source honors seed-artist exclusion",
      all(r['artist'].lower() != 'taylor swift' for r in (chart_recs or [])))

excl = frozenset({'sabrina carpenter'})
chart_recs2 = rec._get_lastfm_chart_recommendations(
    'Taylor Swift', 'Cruel Summer', prof, exclude_artists=excl)
check("chart source honors exclude_artists",
      chart_recs2 is not None
      and all(r['artist'].lower() != 'sabrina carpenter'
              for r in chart_recs2))

# Round-robin merge order: lastfm -> apple -> chart
m = rec._merge_recommendations(
    [{'artist': 'A1', 'name': 's1'}],
    [{'artist': 'B1', 'name': 's2'}],
    [{'artist': 'C1', 'name': 's3'}], limit=3)
check("merge interleaves L->A->C",
      [r['artist'] for r in m] == ['A1', 'B1', 'C1'], repr(m))

# ── 8. Fresh-release filtering (new music, not viral oldies) ────────────────

print("== fresh-release filtering ==")
from datetime import date, timedelta
from services.lyrics_service import canonicalize_track_names

def _dated(artist, song, days_ago, genres=None):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return {'artist': artist, 'song': song,
            'genres': genres or ['Pop'], 'release_date': d}

check("parse ISO date", lc._parse_release_date("2025-10-17") == date(2025, 10, 17))
check("parse ISO datetime+tz",
      lc._parse_release_date("2025-10-03T00:00:00-07:00") == date(2025, 10, 3))
check("parse None/garbage",
      lc._parse_release_date(None) is None and lc._parse_release_date("soon") is None)

fresh_entry = _dated('A', 'new hit', 30)
old_entry = _dated('B', 'oldie', 900)
nodate_entry = {'artist': 'C', 'song': 'mystery', 'genres': ['Pop']}
check("recent song is fresh", lc._is_fresh(fresh_entry))
check("3-year-old song is not fresh", not lc._is_fresh(old_entry))
check("dateless song is not fresh", not lc._is_fresh(nodate_entry))

# 12 fresh + 4 oldies -> fresh pool serves only the new ones
import time as _t
mixed = ([_dated(f'Fresh Artist {i}', f'Fresh Hit {i}', 30 + i) for i in range(12)]
         + [_dated(f'Old Artist {i}', f'Oldie {i}', 900 + i) for i in range(4)])
_reset_mem()
lc._mem['chart'] = mixed
lc._mem['chart_ts'] = _t.time()
fresh = lc.get_fresh_songs()
check("fresh pool excludes oldies",
      len(fresh) == 12 and all('Fresh' in s['artist'] for s in fresh), repr(len(fresh)))
check("fresh pool keeps release_date",
      all(s.get('release_date') for s in fresh))

# too few fresh -> [] so callers fall back to the full chart
thin = ([_dated('Fresh Artist 1', 'Fresh Hit 1', 30)]
        + [_dated(f'Old Artist {i}', f'Oldie {i}', 900 + i) for i in range(20)])
lc._mem['chart'] = thin
lc._mem['chart_ts'] = _t.time()
check("thin fresh pool returns []", lc.get_fresh_songs() == [])

# genre-scoped fresh pool
genre_mixed = ([_dated(f'Pop Star {i}', f'Pop Hit {i}', 60, ['Pop']) for i in range(5)]
               + [_dated(f'Rap Star {i}', f'Rap Hit {i}', 60, ['Hip-Hop/Rap']) for i in range(5)]
               + [_dated('Old Pop', 'Old Pop Hit', 900, ['Pop'])])
lc._mem['chart'] = genre_mixed
lc._mem['chart_ts'] = _t.time()
pop_fresh = lc.get_fresh_songs(genre='pop')
check("genre fresh pool is pop-only and fresh",
      len(pop_fresh) == 5 and all('Pop Star' in s['artist'] for s in pop_fresh),
      repr(pop_fresh))

# /random draws only from the fresh pool when it is healthy
lc._mem['chart'] = mixed
lc._mem['chart_ts'] = _t.time()
picks = {get_random_song(user_id=424242)['artist'] for _ in range(25)}
check("/random never serves oldies from a healthy fresh pool",
      picks and all('Fresh' in a for a in picks), repr(picks))

# quiz draws from the fresh pool
qsongs = qs.get_quiz_songs()
check("quiz songs are fresh releases",
      qsongs and all('Fresh' in s['artist'] for s in qsongs), repr(len(qsongs)))

# mangled multi-artist credit from lrclib is normalized
ca, ct = canonicalize_track_names("Ella Langley - & Morgan Wallen",
                                  "I Can't Love You Anymore")
check("artist ' - & ' mangling is fixed",
      ca == "Ella Langley & Morgan Wallen" and ct == "I Can't Love You Anymore",
      repr((ca, ct)))

# parsers capture release dates from both feeds
prim = lc._parse_apple_marketing({'feed': {'results': [
    {'name': 'Hit', 'artistName': 'Star', 'releaseDate': '2026-01-15',
     'genres': [{'name': 'Pop'}, {'name': 'Music'}]}]}})
check("primary parser captures releaseDate",
      prim and prim[0]['release_date'] == '2026-01-15', repr(prim))
fb = lc._parse_itunes_rss({'feed': {'entry': [
    {'im:name': {'label': 'Hit'}, 'im:artist': {'label': 'Star'},
     'im:releaseDate': {'label': '2026-01-15T00:00:00-07:00'},
     'category': {'attributes': {'term': 'Pop'}}}]}})
check("fallback parser captures im:releaseDate",
      fb and fb[0]['release_date'] == '2026-01-15T00:00:00-07:00', repr(fb))

# ── 9. Artist top songs are live-first (no fixed 5) ──────────────────────────

print("== artist top songs live-first ==")
import handlers as _h

class _FakeResp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def json(self):
        return self._p

_real_get = _h.requests.get
_h._top_songs_cache.clear()
os.environ['LASTFM_API_KEY'] = 'test-key'

def _fake_lastfm(url, params=None, timeout=None):
    assert params.get('method') == 'artist.getTopTracks'
    return _FakeResp({'toptracks': {'track': [
        {'name': 'New Hit A'}, {'name': 'New Hit B'}, {'name': 'New Hit A'},
        {'name': 'New Hit C'}, {'name': 'Old Classic'}, {'name': 'New Hit D'},
        {'name': 'New Hit E'}]}})

_h.requests.get = _fake_lastfm
try:
    live = _h._fetch_artist_top_songs('Tyla')  # in static DB, must still go live first
    check("known artist uses live top tracks, not static list",
          live == ['New Hit A', 'New Hit B', 'New Hit C', 'Old Classic', 'New Hit D'],
          repr(live))
    check("live top songs are cached",
          _h._fetch_artist_top_songs('Tyla') == live)
finally:
    _h.requests.get = _real_get
    _h._top_songs_cache.clear()

# live miss -> iTunes fallback
def _fake_itunes(url, params=None, timeout=None):
    if 'audioscrobbler' in url:
        return _FakeResp({}, status=500)
    return _FakeResp({'results': [
        {'artistName': 'Tyla', 'trackName': 'iTunes Song 1'},
        {'artistName': 'Tyla', 'trackName': 'iTunes Song 2'}]})
_h.requests.get = _fake_itunes
try:
    fb = _h._fetch_artist_top_songs('Tyla')
    check("Last.fm miss falls back to live iTunes search",
          fb == ['iTunes Song 1', 'iTunes Song 2'], repr(fb))
finally:
    _h.requests.get = _real_get
    _h._top_songs_cache.clear()

# everything misses -> static DB as last resort (never [])
def _fake_dead(url, params=None, timeout=None):
    return _FakeResp({}, status=500)
_h.requests.get = _fake_dead
try:
    static = _h._fetch_artist_top_songs('Tyla')
    check("total live miss falls back to static list, never empty",
          static == ['Water', 'Truth or Dare', 'Jump', 'ART', 'Getting Late'],
          repr(static))
    check("unknown artist with dead sources -> []",
          _h._fetch_artist_top_songs('Some Unknown Artist XYZ') == [])
finally:
    _h.requests.get = _real_get
    _h._top_songs_cache.clear()

_reset_mem()

print(f"\n{PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
