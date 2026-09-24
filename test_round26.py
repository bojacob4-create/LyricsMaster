"""Round-26 tests: recommendation logs must name the actual picks.

The user's standing instruction is "check the logs" — but the logs only
recorded counts ("Merged 5 Last.fm + 5 Apple → 5"), never the song names,
which once led to a wrong reconstruction being presented as fact.  Now
_get_similar_songs_uncached logs a [REC] Picks line with every final
"Artist - Title", so the logs alone answer "what did the user see?".
"""
import logging
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import services.recommendation_service as rs

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def _candidates(*pairs):
    return [{"artist": a, "name": n} for a, n in pairs]


def run_pipeline():
    cap = _Cap()
    logger = logging.getLogger("services.recommendation_service")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(cap)
    try:
        with patch.object(rs, "_detect_genre", return_value="rnb"), \
             patch.object(rs, "_build_song_profile",
                          return_value={"genre": "rnb", "mood": "romantic",
                                        "style": "alt_rnb", "vocal": "female",
                                        "era": "modern"}), \
             patch.object(rs, "_get_lastfm_recommendations",
                          return_value=_candidates(
                              ("SZA", "Snooze"), ("Tinashe", "Nasty"))), \
             patch.object(rs, "_get_apple_recommendations",
                          return_value=_candidates(
                              ("Summer Walker", "Girls Need Love"),
                              ("FLO", "Cardboard Box"))), \
             patch.object(rs, "_get_lastfm_chart_recommendations",
                          return_value=_candidates(
                              ("Chloe x Halle", "Do It"))):
                merged = rs._get_similar_songs_uncached(
                    "Tyla", "Water", "romantic", limit=5)
    finally:
        logger.removeHandler(cap)
        logger.setLevel(old_level)
    picks_lines = [m for m in (r for r in cap.records)
                   if "[REC] Picks for" in m]
    return merged, picks_lines


merged, picks_lines = run_pipeline()

# ── 1. A Picks line is logged ──────────────────────────────────────────────
check("a [REC] Picks line is logged", len(picks_lines) == 1,
      f"found {len(picks_lines)}")
line = picks_lines[0] if picks_lines else ""

# ── 2. It names the source song ────────────────────────────────────────────
check("Picks line names the source song", "'Tyla - Water'" in line, repr(line[:80]))

# ── 3. Every merged pick appears by name (the whole point) ─────────────────
missing = [f"{r.get('artist')} - {r.get('name')}" for r in merged
           if f"{r.get('artist')} - {r.get('name')}" not in line]
check("every final pick is named in the log", not missing,
      f"missing from log line: {missing}")

# ── 4. Format is greppable: 'Artist - Title' pairs ─────────────────────────
check("picks are pipe-separated Artist - Title pairs",
      " | " in line and "SZA - Snooze" in line, repr(line[:120]))

print(f"\nround26: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
