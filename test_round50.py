#!/usr/bin/env python3
"""Round 50: /newmusic marks genuinely new releases with 🆕.

Free iTunes releaseDate lookups (no OpenAI, no key). 'New' = released
within the last 2 years, same bar as /playlist's 🆕 slice.
"""

import datetime
import os
import re
import sys

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


CUTOFF = (datetime.date.today()
          - datetime.timedelta(days=365 * d.NEWMUSIC_NEW_YEARS)).isoformat()
NEW_DATE = datetime.date.today().isoformat()
OLD_DATE = "2015-06-01"

calls = {"n": 0}


def fake_release(artist, title):
    calls["n"] += 1
    t = (title or "").lower()
    if t == "brand new hit":
        return NEW_DATE
    if t == "old classic":
        return OLD_DATE
    return None


_real = d._itunes_earliest_release
d._itunes_earliest_release = fake_release
try:
    # ── flag logic ────────────────────────────────────────────────
    songs = [{"artist": "A", "song": "Brand New Hit"},
             {"artist": "B", "song": "Old Classic"},
             {"artist": "C", "song": "Total Mystery"}]
    originals = [dict(s) for s in songs]
    out = d._annotate_new_flags(songs)
    check("flags: new/old/unknown",
          out[0]["is_new"] is True and out[1]["is_new"] is False
          and out[2]["is_new"] is False,
          str([s.get("is_new") for s in out]))
    check("flags: inputs not mutated (pool-safe)",
          all("is_new" not in s for s in songs),
          str(songs))
    check("flags: returns copies", all(o is not s for o, s in zip(out, songs)))

    # ── cutoff boundary ───────────────────────────────────────────
    def fake_boundary(artist, title):
        return {"on": CUTOFF,
                "before": (datetime.date.fromisoformat(CUTOFF)
                           - datetime.timedelta(days=1)).isoformat()}[title]
    d._itunes_earliest_release = fake_boundary
    b = d._annotate_new_flags([{"artist": "A", "song": "on"},
                               {"artist": "A", "song": "before"}])
    check("flags: cutoff boundary (on=new, day-before=old)",
          b[0]["is_new"] is True and b[1]["is_new"] is False,
          f"cutoff={CUTOFF}")

    # ── get_new_music shape (stubbed chart + lookup) ──────────────
    d._itunes_earliest_release = fake_release
    _old_trend = d.get_trending_songs
    d.get_trending_songs = lambda: (
        [{"artist": "A", "song": "Brand New Hit"},
         {"artist": "B", "song": "Old Classic"}], True)
    try:
        songs, is_live = d.get_new_music(None, 2)
        check("get_new_music: (songs, is_live) with is_new flags",
              is_live is True and len(songs) == 2
              and songs[0]["is_new"] is True
              and songs[1]["is_new"] is False,
              str([(s["song"], s.get("is_new")) for s in songs]))
    finally:
        d.get_trending_songs = _old_trend

    # ── fallback path also annotated ──────────────────────────────
    d.get_trending_songs = lambda: ([], False)
    try:
        songs, is_live = d.get_new_music(None, 3)
        check("get_new_music: fallback annotated, honestly not live",
              is_live is False and len(songs) == 3
              and all("is_new" in s for s in songs))
    finally:
        d.get_trending_songs = _old_trend
finally:
    d._itunes_earliest_release = _real

# ── cache: real function, same song twice ──────────────────────────
d._NEWMUSIC_YEAR_CACHE.clear()
d._itunes_earliest_release("No Such Artist Xyz", "No Such Song Abc")
n1 = len(d._NEWMUSIC_YEAR_CACHE)
d._itunes_earliest_release("No Such Artist Xyz", "No Such Song Abc")
check("cache: repeat lookup served from memory",
      len(d._NEWMUSIC_YEAR_CACHE) == n1 == 1)

# ── live smoke (non-fatal): format only ────────────────────────────
d._NEWMUSIC_YEAR_CACHE.clear()
rel = d._itunes_earliest_release("Billie Eilish", "BIRDS OF A FEATHER")
check("live: release date format sane",
      rel is None or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", rel or "")),
      str(rel))
print(f"  (live smoke returned: {rel})")

# ── remaster guard: earliest match wins ────────────────────────────
d._NEWMUSIC_YEAR_CACHE.clear()
rel = d._itunes_earliest_release("Queen", "Bohemian Rhapsody")
check("live: old song not marked new via remaster",
      rel is None or rel < CUTOFF, str(rel))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
