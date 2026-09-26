"""Round-69 tests: zero-cost speedups.

Scope (user-approved "go after it", honoring the honest no's):
- Translation: OpenAI fallback chunks go concurrently when the breaker is
  open (same tokens/cost, no Google burst pause).  Those tests live in
  test_round68.py section 18, beside the other translation tests.
- Dashboard: the 9.5s get_similar_songs leg was dominated by release-year
  freshness lookups (3.1s of iTunes calls on the critical path).
  (1) _fetch_release_years now uses 16 workers (one wave, same requests).
  (2) The release-year cache persists to disk — years are immutable, so
  the in-memory cache dying on every restart was pure waste.
  Ranking behavior is unchanged (same values, same TTL semantics).
"""
import concurrent.futures
import os
import sys
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import services.recommendation_service as R

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _snapshot_cache():
    return dict(R._release_year_cache)


def _restore_cache(snap):
    R._release_year_cache.clear()
    R._release_year_cache.update(snap)


# ── 1. Year cache disk round-trip ──────────────────────────────────────────
import tempfile as _tempfile
import json as _json
_snap = _snapshot_cache()
_bp = _tempfile.mktemp(suffix=".json")
try:
    R._release_year_cache.clear()
    now = time.time()
    R._release_year_cache[("tyla", "water")] = (now, 2023)
    R._release_year_cache[("rema", "calm down")] = (now, 2022)
    with patch.object(R, "_YEAR_CACHE_PATH", _bp):
        R._persist_year_cache()
        check("years: cache file written", os.path.exists(_bp))
        R._release_year_cache.clear()
        R._load_year_cache()
        check("years: entries restored from disk",
              R._release_year_cache.get(("tyla", "water")) == (now, 2023)
              and R._release_year_cache.get(("rema", "calm down"))[1] == 2022)
        # stale entries are pruned on save, not resurrected
        R._release_year_cache[("old", "song")] = (now - R._RELEASE_YEAR_TTL - 1, 1999)
        R._persist_year_cache()
        with open(_bp) as f:
            raw = _json.load(f)
        check("years: stale entries pruned on save",
              not any(k.startswith("old\x1f") for k in raw))
        R._release_year_cache.clear()
        R._load_year_cache()
        check("years: stale entries not reloaded",
              ("old", "song") not in R._release_year_cache)
finally:
    if os.path.exists(_bp):
        os.remove(_bp)
    _restore_cache(_snap)

# ── 2. _fetch_release_years: 16 workers, same results ──────────────────────
_snap = _snapshot_cache()
try:
    R._release_year_cache.clear()
    seen = {}
    RealEx = concurrent.futures.ThreadPoolExecutor

    class RecEx(RealEx):
        def __init__(self, max_workers=None, *a, **k):
            seen["max_workers"] = max_workers
            super().__init__(max_workers=max_workers, *a, **k)

    def _fake_year(a, s):
        R._release_year_cache[(a.lower().strip(), s.lower().strip())] = (
            time.time(), 2000 + len(a) % 25)

    pairs = [(f"Artist{i}", f"Song{i}") for i in range(5)]
    with patch.object(R, "_fetch_release_year", side_effect=_fake_year), \
         patch("concurrent.futures.ThreadPoolExecutor", RecEx), \
         patch.object(R, "_YEAR_CACHE_PATH", _tempfile.mktemp(suffix=".json")):
        out = R._fetch_release_years(pairs)
    check("years: 16 workers, one wave", seen.get("max_workers") == 16,
          f"got {seen.get('max_workers')}")
    check("years: all pairs resolved",
          len(out) == 5 and all(v is not None for v in out.values()),
          repr(out))
finally:
    _restore_cache(_snap)

# ── 3. Ranking behavior preserved: era penalty still applies ───────────────
def _fake_year2(artist, song):
    years = {("tyla", "water"): 2023,
             ("newkid", "fresh track"): 2023,
             ("oldtimer", "classic"): 2003}
    y = years.get((artist.lower(), song.lower()))
    # mirror the real function: populate the cache
    R._release_year_cache[(artist.lower().strip(), song.lower().strip())] = (
        time.time(), y)
    return y

scored = [
    (90.0, {"artist": "Newkid", "name": "Fresh Track"}, "afrobeats"),
    (88.0, {"artist": "Oldtimer", "name": "Classic"}, "afrobeats"),
]
with patch.object(R, "_fetch_release_year", side_effect=_fake_year2), \
     patch.object(R, "_YEAR_CACHE_PATH", _tempfile.mktemp(suffix=".json")):
    R._apply_freshness("Tyla", "Water", scored)
check("freshness: era-matched candidate untouched", scored[0][0] == 90.0,
      f"got {scored[0][0]}")
check("freshness: 20-year gap penalized by max 30",
      scored[1][0] == 88.0 - 30.0, f"got {scored[1][0]}")
check("freshness: ordering still era-aligned", scored[0][0] > scored[1][0])

# ── 4. Apple chart disk cache ──────────────────────────────────────────────
_snap_a = dict(R._apple_cache)
_bp3 = _tempfile.mktemp(suffix=".json")
try:
    with patch.object(R, "_APPLE_CACHE_PATH", _bp3):
        R._apple_cache.clear()
        cands = [{"name": "Song A", "artist": "Artist A", "reason": "r"}]
        R._save_apple_cache(time.time(), cands)
        check("apple: chart file written", os.path.exists(_bp3))
        R._apple_cache.clear()
        R._load_apple_cache()
        check("apple: chart restored from disk",
              R._apple_cache.get("global", (0, []))[1] == cands)
        # a stale chart is not resurrected
        R._apple_cache.clear()
        R._save_apple_cache(time.time() - R._CACHE_TTL - 1, cands)
        R._load_apple_cache()
        check("apple: stale chart ignored", "global" not in R._apple_cache)
        # the fetch path persists, then serves from memory
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"feed": {"results": [
            {"name": "Hit Song", "artistName": "Star Singer"}]}}
        R._apple_cache.clear()
        if os.path.exists(_bp3):
            os.remove(_bp3)
        with patch.object(R.requests, "get",
                          return_value=fake_resp) as g:
            out1 = R._fetch_apple_top_songs()
            out2 = R._fetch_apple_top_songs()
        check("apple: fetch parses results",
              out1 == [{"name": "Hit Song", "artist": "Star Singer",
                        "reason": "Trending on Apple Music Top 100"}],
              repr(out1))
        check("apple: second call served from memory", g.call_count == 1)
        check("apple: fetch persisted to disk", os.path.exists(_bp3))
finally:
    if os.path.exists(_bp3):
        os.remove(_bp3)
    R._apple_cache.clear()
    R._apple_cache.update(_snap_a)

print(f"\nround69: {passed} passed, {failed} failed")
