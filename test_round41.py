"""Round 41: /playlist — artist playlist (all-time + new + trending).

- Count parsing: default 12, max 15 (100 -> capped + honest notice),
  trailing numbers that belong to the artist ("Blink 182") recoverable
- Slice quotas split the count into thirds
- Dedup across slices, rebalancing of shortfalls, interleave order
- Formatting: header, per-song slice notes, honest capped/short notices
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import playlist_service as PS

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


# ── argument parsing ──────────────────────────────────────────────────────
a, c, cap, fb = PS.parse_playlist_args(['Tyla'])
check("bare artist -> default 12", (a, c, cap, fb) == ('Tyla', 12, False, None))

a, c, cap, fb = PS.parse_playlist_args(['Tyla', '13'])
check("Tyla 13", (a, c, cap) == ('Tyla', 13, False) and fb == 'Tyla 13')

a, c, cap, fb = PS.parse_playlist_args(['Tyla', '100'])
check("Tyla 100 -> capped 15", (a, c, cap) == ('Tyla', 15, True)
      and fb == 'Tyla 100')

a, c, cap, fb = PS.parse_playlist_args(['Tyla', '0'])
check("Tyla 0 -> default 12", (a, c, cap) == ('Tyla', 12, False))

a, c, cap, fb = PS.parse_playlist_args(['Tyla', '15'])
check("Tyla 15 -> 15 no cap notice", (a, c, cap) == ('Tyla', 15, False))

a, c, cap, fb = PS.parse_playlist_args(['Tyla', 'abc'])
check("non-numeric tail stays in artist", a == 'Tyla abc' and c == 12)

a, c, cap, fb = PS.parse_playlist_args(['Blink', '182'])
check("Blink 182: 182 treated as count, fallback kept",
      (a, c, cap) == ('Blink', 15, True) and fb == 'Blink 182')

a, c, cap, fb = PS.parse_playlist_args(['The', '1975', '10'])
check("The 1975 10", (a, c) == ('The 1975', 10))

a, c, cap, fb = PS.parse_playlist_args(['1975'])
check("single numeric token is the artist", (a, c) == ('1975', 12))

a, c, cap, fb = PS.parse_playlist_args([])
check("no args -> empty artist, default 12", (a, c) == ('', 12))

# ── quotas ────────────────────────────────────────────────────────────────
check("quotas 12 -> 4/4/4", PS._quotas(12) == (4, 4, 4))
check("quotas 13 -> 5/4/4", PS._quotas(13) == (5, 4, 4))
check("quotas 14 -> 5/5/4", PS._quotas(14) == (5, 5, 4))
check("quotas 15 -> 5/5/5", PS._quotas(15) == (5, 5, 5))
check("quotas 3 -> 1/1/1", PS._quotas(3) == (1, 1, 1))
check("quotas 1 -> 1/0/0", PS._quotas(1) == (1, 0, 0))

# ── title tidying ─────────────────────────────────────────────────────────
check("all-caps tidied", PS._tidy_caps("RIGHT NOW") == "Right Now")
check("apostrophe kept inside word",
      PS._tidy_caps("I DON'T CARE") == "I Don't Care")
check("mixed case untouched", PS._tidy_caps("Truth or dare") == "Truth or dare")
check("normal title untouched", PS._tidy_caps("Water") == "Water")
check("empty safe", PS._tidy_caps("") == "")

# ── build: mocked fetchers ────────────────────────────────────────────────
_ALL = ['Water', 'Push 2 Start', 'Truth or Dare', 'Show Me Love', 'Jump',
        'Art', 'On and On', 'Butterflies', 'Safer', 'No.1',
        'Breathe Me', 'Aiko']
_NEW = [(f'New Song {i}', '2026-03-01') for i in range(1, 13)]
_TR = ['Chanel', 'Water', 'Is It'] + [f'Hot Track {i}' for i in range(1, 10)]

PS._lastfm_all_time = lambda artist, limit: _ALL[:limit]
PS._itunes_new_songs = lambda artist, limit: ('Tyla', _NEW[:limit])
PS._chart_trending = lambda artist, limit: _TR[:limit]

display, songs, meta = PS.build_artist_playlist('tyla', 12)
check("build 12 songs", len(songs) == 12)
check("canonical artist from iTunes", display == 'Tyla')
titles = [s['song'] for s in songs]
check("dedup across slices (Water once)",
      len(titles) == len({t.lower() for t in titles}))
check("interleave opens with trending",
      songs[0]['note'] == PS.NOTE_TRENDING)
notes = {s['note'] for s in songs}
check("all three slice notes present",
      notes == {PS.NOTE_ALL_TIME, PS.NOTE_NEW, PS.NOTE_TRENDING})
counts = {n: sum(1 for s in songs if s['note'] == n) for n in notes}
check("slice quotas honored (4/4/4)",
      counts == {PS.NOTE_ALL_TIME: 4, PS.NOTE_NEW: 4, PS.NOTE_TRENDING: 4})
check("every song tagged to the artist",
      all(s['artist'] == 'Tyla' for s in songs))

# Rebalance: new-slice dry -> filled from all-time, stays honest.
PS._itunes_new_songs = lambda artist, limit: ('Tyla', [])
display, songs, meta = PS.build_artist_playlist('tyla', 12)
check("dry new slice still yields 12", len(songs) == 12)
check("rebalance flagged in meta", meta['rebalanced'] is True)
check("no new-slice songs when the slice is dry",
      all(s['note'] != PS.NOTE_NEW for s in songs))
check("nothing unfilled -> no shortfall notice", meta['short'] == {})

# True exhaustion: pools too small -> shortfall recorded honestly.
PS._lastfm_all_time = lambda artist, limit: ['Water', 'Jump']
PS._chart_trending = lambda artist, limit: []
display, songs, meta = PS.build_artist_playlist('tyla', 12)
check("exhausted pools -> short list, no crash", 0 < len(songs) < 12)
check("unfilled shortfall recorded", sum(meta['short'].values()) > 0)

# ── qualifier-aware dedup ───────────────────────────────────────────────
check("dedup key strips live qualifier",
      PS._dedup_key("Stan (Live At Wembley 2014)") == PS._dedup_key("Stan"))
check("dedup key strips dash qualifier",
      PS._dedup_key("Hello - Live at the BRITs") == PS._dedup_key("Hello"))
check("non-live qualifier untouched",
      PS._dedup_key("Song - Studio Version") != PS._dedup_key("Song"))
check("plain titles still distinct",
      PS._dedup_key("Water") != PS._dedup_key("Fire"))

# The user's Eminem case: the live re-release must not duplicate "Stan".
PS._lastfm_all_time = lambda artist, limit: ['Stan', 'Lose Yourself',
                                             'Mockingbird'][:limit]
PS._itunes_new_songs = lambda artist, limit: (
    'Eminem', [('Stan (Live At Wembley 2014)', '2025-08-25')][:limit])
PS._chart_trending = lambda artist, limit: []
display, songs, meta = PS.build_artist_playlist('eminem', 6)
stan = [s for s in songs if PS._dedup_key(s['song']) == 'stan']
check("live qualifier variant does not duplicate (Eminem case)",
      len(stan) == 1)
check("plain all-time version wins the dedup",
      stan and stan[0]['song'] == 'Stan'
      and stan[0]['note'] == PS.NOTE_ALL_TIME)

# Total miss: every source empty -> no songs (caller shows not-found).
PS._lastfm_all_time = lambda artist, limit: []
PS._itunes_new_songs = lambda artist, limit: (None, [])
PS._chart_trending = lambda artist, limit: []
display, songs, meta = PS.build_artist_playlist('tyla', 12)
check("all sources dry -> no songs", songs == [])

# Empty query -> no songs, no crash.
display, songs, meta = PS.build_artist_playlist('   ', 12)
check("empty artist -> no songs", songs == [])

# ── formatting ────────────────────────────────────────────────────────────
PS._lastfm_all_time = lambda artist, limit: _ALL[:limit]
PS._itunes_new_songs = lambda artist, limit: ('Tyla', _NEW[:limit])
PS._chart_trending = lambda artist, limit: _TR[:limit]
display, songs, meta = PS.build_artist_playlist('tyla', 13)
text = PS.format_playlist(display, songs, capped=False, meta=meta)
check("header names the artist", "Tyla — Your Playlist" in text)
check("numbered lines", "1. " in text and "13. " in text)
check("slice notes rendered",
      PS.NOTE_TRENDING in text and PS.NOTE_ALL_TIME in text)
check("footer invites taps", "Tap a song below" in text)
check("no cap notice when not capped", "📏" not in text)

text = PS.format_playlist(display, songs, capped=True, meta=meta)
check("capped notice is honest",
      "15 is the max that works in chat" in text)

text = PS.format_playlist(display, songs, capped=False,
                           meta={'short': {'new': 2}, 'rebalanced': True})
check("shortfall notice names the slice", "new releases" in text)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
