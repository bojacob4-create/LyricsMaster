#!/usr/bin/env python3
"""Round 51: /newmusic rotates through the live slice per user.

Repeated calls with the same user_id serve the next unseen window in
chart order (no more byte-identical repeats); the slice cycles when
exhausted and the memory resets with the chart cache window.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")

import services.discovery_service as d  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


def mk(i):
    return {"artist": f"Artist{i}", "song": f"Song{i}",
            "note": "Charting now on Apple Music"}


LIVE12 = [mk(i) for i in range(12)]
d._itunes_earliest_release = lambda a, t: None  # no network in this suite

# ── rotation over the genre-live path ───────────────────────────────
_old_live = d._get_live_genre_songs
d._get_live_genre_songs = lambda g, deep=False: list(LIVE12)
try:
    d._NEWMUSIC_SEEN.clear()
    c1, lv1 = d.get_new_music("pop", 5, user_id=111)
    c2, _ = d.get_new_music("pop", 5, user_id=111)
    c3, _ = d.get_new_music("pop", 5, user_id=111)
    k = lambda c: [(s["artist"], s["song"]) for s in c]
    check("live: 1st and 2nd calls disjoint",
          lv1 is True and not set(k(c1)) & set(k(c2)),
          f"{k(c1)} vs {k(c2)}")
    check("live: chart order preserved within each window",
          k(c1) == [(f"Artist{i}", f"Song{i}") for i in range(5)]
          and k(c2) == [(f"Artist{i}", f"Song{i}") for i in range(5, 10)])
    check("live: 3rd call cycles (2 unseen + wrap)",
          k(c3) == [(f"Artist{i}", f"Song{i}") for i in (10, 11, 0, 1, 2)],
          str(k(c3)))
    # per-genre isolation
    c4, _ = d.get_new_music("rock", 5, user_id=111)
    check("live: rotation memory is per-genre",
          k(c4) == [(f"Artist{i}", f"Song{i}") for i in range(5)])
    # per-user isolation
    c5, _ = d.get_new_music("pop", 5, user_id=222)
    check("live: rotation memory is per-user",
          k(c5) == [(f"Artist{i}", f"Song{i}") for i in range(5)])
    # no user_id -> old behaviour (first window, no memory written)
    d._NEWMUSIC_SEEN.clear()
    ca, _ = d.get_new_music("pop", 5)
    cb, _ = d.get_new_music("pop", 5)
    check("live: no user_id serves first window both times",
          k(ca) == k(cb) == [(f"Artist{i}", f"Song{i}") for i in range(5)]
          and not d._NEWMUSIC_SEEN)
    # TTL reset: stale memory starts over at the top
    d._NEWMUSIC_SEEN.clear()
    d.get_new_music("pop", 5, user_id=111)
    d.get_new_music("pop", 5, user_id=111)
    for key in list(d._NEWMUSIC_SEEN):
        ts, seen = d._NEWMUSIC_SEEN[key]
        d._NEWMUSIC_SEEN[key] = (ts - d._NEWMUSIC_ROT_TTL - 1, seen)
    c6, _ = d.get_new_music("pop", 5, user_id=111)
    check("live: stale memory resets to top of chart",
          k(c6) == [(f"Artist{i}", f"Song{i}") for i in range(5)])
finally:
    d._get_live_genre_songs = _old_live

# ── rotation over the no-genre trending path ────────────────────────
# Round 53: the bare path now prefers the deep US chart; the old 10-song
# trending slice is only the fallback.  Patch the deep chart (primary).
_old_deep = d.get_us_chart_deep
_old_trend = d.get_trending_songs
d.get_us_chart_deep = lambda: list(LIVE12[:10])
d.get_trending_songs = lambda: (list(LIVE12[:10]), True)
try:
    d._NEWMUSIC_SEEN.clear()
    t1, _ = d.get_new_music(None, 5, user_id=111)
    t2, _ = d.get_new_music(None, 5, user_id=111)
    k = lambda c: [(s["artist"], s["song"]) for s in c]
    check("trending: repeats rotate, then cycle",
          not set(k(t1)) & set(k(t2))
          and k(t2) == [(f"Artist{i}", f"Song{i}") for i in range(5, 10)])
finally:
    d.get_us_chart_deep = _old_deep
    d.get_trending_songs = _old_trend

# ── regression: is_new flags still attached ────────────────────────
d._NEWMUSIC_SEEN.clear()
d._get_live_genre_songs = lambda g, deep=False: list(LIVE12[:5])
try:
    songs, _ = d.get_new_music("pop", 5, user_id=111)
    check("regression: is_new present on rotated picks",
          all("is_new" in s for s in songs))
finally:
    d._get_live_genre_songs = _old_live

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
