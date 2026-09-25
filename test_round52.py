#!/usr/bin/env python3
"""Round 52: /newmusic goes deep + fresh-first.

- Genre's OWN Apple chart (Pop Top ~100) instead of tag-filtering the US
  chart -> deep live pool, repeats gone.
- Fresh-first: releases from the last NEWMUSIC_NEW_DAYS days lead,
  newest first; then chart order. One honest 🆕 threshold (60 days).
- /top path (deep=False) contract unchanged.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")

import services.artist_service as a  # noqa: E402
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


def mk(i, note="Charting now on Apple Music"):
    return {"artist": f"Artist{i}", "song": f"Song{i}", "note": note}


TODAY = datetime.date.today()
CUTOFF = (TODAY - datetime.timedelta(days=d.NEWMUSIC_NEW_DAYS)).isoformat()
D = lambda days_ago: (TODAY - datetime.timedelta(days=days_ago)).isoformat()

check("threshold: NEWMUSIC_NEW_DAYS is 60", d.NEWMUSIC_NEW_DAYS == 60)

# ── _fresh_first ordering (stubbed dates) ────────────────────────────
dates = {"Song0": D(10), "Song1": D(400), "Song2": D(5), "Song3": D(700),
         "Song4": None, "Song5": D(30)}
_real_rel = d._itunes_earliest_release
d._itunes_earliest_release = lambda ar, t: dates.get(t)
try:
    out = d._fresh_first([mk(i) for i in range(6)])
    got = [(s["song"], s.get("is_new")) for s in out]
    check("fresh-first: fresh (newest first), then chart order",
          got == [("Song2", True), ("Song0", True), ("Song5", True),
                  ("Song1", False), ("Song3", False), ("Song4", False)],
          str(got))
    check("fresh-first: no temp keys leak",
          all("_rel" not in s for s in out))
    # boundary: exactly at cutoff counts as new
    d._itunes_earliest_release = lambda ar, t: CUTOFF if t == "Edge" else D(400)
    b = d._mark_fresh([{"artist": "A", "song": "Edge"},
                       {"artist": "A", "song": "Old"}])
    check("badge: cutoff day counts as new",
          b[0]["is_new"] is True and b[1]["is_new"] is False)
finally:
    d._itunes_earliest_release = _real_rel

# ── deep genre chart path (stubbed chart) ────────────────────────────
deep_chart = [{"artist": f"PA{i}", "song": f"PS{i}", "genres": []}
              for i in range(40)]
_old_gc = a._get_cached_genre_chart
a._get_cached_genre_chart = lambda gid, country="us": list(deep_chart)
_old_tag = a._get_lastfm_genre_songs
a._get_lastfm_genre_songs = lambda *a_, **k: []
try:
    songs = a._get_live_genre_songs("pop", deep=True)
    check("deep: pop serves 30 from its own chart",
          songs is not None and len(songs) == 30
          and songs[0]["artist"] == "PA0",
          str(len(songs) if songs else None))
    check("deep: /top path untouched (no deep kwarg -> old contract)",
          a._get_live_genre_songs("pop") is not None)
finally:
    a._get_cached_genre_chart = _old_gc
    a._get_lastfm_genre_songs = _old_tag

# kpop has no RSS genre -> country-chart tag path still works deep
kr_chart = ([{"artist": f"KA{i}", "song": f"KS{i}", "genres": ["K-Pop"]}
             for i in range(20)]
            + [{"artist": f"UA{i}", "song": f"US{i}", "genres": ["Pop"]}
               for i in range(80)])
_old_cc = a._get_cached_chart
a._get_cached_chart = lambda country="us": list(kr_chart)
a._get_lastfm_genre_songs = lambda *a_, **k: []
try:
    songs = a._get_live_genre_songs("kpop", deep=True)
    check("deep: kpop falls back to Korea chart tag path",
          songs is not None and len(songs) == 20
          and all(s["artist"].startswith("KA") for s in songs),
          str(len(songs) if songs else None))
finally:
    a._get_cached_chart = _old_cc
    a._get_lastfm_genre_songs = _old_tag

# ── end-to-end: fresh lead the card ──────────────────────────────────
d._NEWMUSIC_SEEN.clear()
a._get_cached_genre_chart = lambda gid, country="us": list(deep_chart)
a._get_lastfm_genre_songs = lambda *a_, **k: []
d._itunes_earliest_release = lambda ar, t: (
    D(3) if t in ("PS1", "PS2") else D(500))
try:
    songs, is_live = d.get_new_music("pop", 5, user_id=777)
    got = [s["song"] for s in songs]
    check("e2e: fresh songs lead, newest first",
          is_live is True and got[:2] == ["PS1", "PS2"]
          and all(s.get("is_new") for s in songs[:2]),
          str(got))
    check("e2e: no repeats on 2nd call (deep pool)",
          [s["song"] for s in d.get_new_music("pop", 5, user_id=777)[0]]
          != got)
finally:
    a._get_cached_genre_chart = _old_gc
    a._get_lastfm_genre_songs = _old_tag
    d._itunes_earliest_release = _real_rel

# ── live: the real Pop chart is deep ─────────────────────────────────
a._genre_chart_cache.clear()
live = a._get_cached_genre_chart("14", "us")
check("live: Pop RSS chart is deep",
      live is not None and len(live) >= 30, str(len(live) if live else None))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
