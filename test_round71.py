"""Round 71 — /history (persistent song-view history).

Covers services/history_service.py:
  1. record_view + get_history ordering (most-recent-first)
  2. recency bump: re-viewing a song moves it to top, no duplicate
  3. cap at 30 entries (oldest dropped)
  4. clear_history returns count, leaves other users untouched
  5. persistence across "restart" (fresh load from the same file)
  6. format_when labels: today / yesterday / date
  7. empty artist/title are ignored
  8. production-state isolation: the live .history.json is never touched

Style matches the other round files: plain asserts, no pytest needed.
Run: python test_round71.py
"""

import os
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import history_service as hs

# ── Production-state isolation ─────────────────────────────────────────────
# record_view persists to disk. Redirect to a temp file so a test run can
# never write to (or create) the live bot's .history.json.
_hs_iso = tempfile.mktemp(suffix=".history.json")
patch.object(hs, "_HISTORY_PATH", _hs_iso).start()

passed, failed = 0, 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


def fresh_user(tag):
    return 900000 + abs(hash(tag)) % 899999


# ── 1. ordering ────────────────────────────────────────────────────────────
u = fresh_user("order")
hs.record_view(u, "Tyla", "Water")
hs.record_view(u, "Adele", "Hello")
h = hs.get_history(u)
check("most-recent-first", [e["title"] for e in h] == ["Hello", "Water"])
check("artist preserved", h[0]["artist"] == "Adele")

# ── 2. recency bump ────────────────────────────────────────────────────────
hs.record_view(u, "Tyla", "Water")  # re-view
h = hs.get_history(u)
check("re-view bumps to top", [e["title"] for e in h] == ["Water", "Hello"])
check("no duplicate entries", len(h) == 2)

# case-insensitive bump
hs.record_view(u, "tyla", "water")
h = hs.get_history(u)
check("bump is case-insensitive", len(h) == 2 and h[0]["title"] == "water")

# ── 3. cap at 30 ───────────────────────────────────────────────────────────
u2 = fresh_user("cap")
for i in range(35):
    hs.record_view(u2, f"Artist{i}", f"Song{i}")
h = hs.get_history(u2)
check("capped at 30", len(h) == 30)
check("newest kept", h[0]["title"] == "Song34")
check("oldest dropped", h[-1]["title"] == "Song5")

# ── 4. clear ───────────────────────────────────────────────────────────────
n = hs.clear_history(u2)
check("clear returns count", n == 30)
check("clear empties", hs.get_history(u2) == [])
check("clear leaves other users alone", len(hs.get_history(u)) == 2)
check("clear on empty returns 0", hs.clear_history(123456789) == 0)

# ── 5. persistence ─────────────────────────────────────────────────────────
u3 = fresh_user("persist")
hs.record_view(u3, "Billie Eilish", "BIRDS OF A FEATHER")
# Simulate a restart: reload the module state from the same file.
import importlib
hs2_path = hs._HISTORY_PATH
data = hs._load()
check("data on disk", str(u3) in data)
h = hs.get_history(u3)
check("survives reload", len(h) == 1 and h[0]["artist"] == "Billie Eilish")

# ── 6. format_when ─────────────────────────────────────────────────────────
now = time.time()
check("today label", hs.format_when(now - 60, now).startswith("today "))
check("yesterday label",
      hs.format_when(now - 86400 - 60, now).startswith("yesterday "))
old = hs.format_when(now - 10 * 86400, now)
check("date label has no today/yesterday",
      not old.startswith("today") and not old.startswith("yesterday")
      and len(old) > 0)
check("format_when never raises on junk", hs.format_when("junk") == "")

# ── 7. junk input ──────────────────────────────────────────────────────────
u4 = fresh_user("junk")
hs.record_view(u4, "", "NoArtist")
hs.record_view(u4, "NoTitle", "")
hs.record_view(u4, "   ", "   ")
check("empty artist/title ignored", hs.get_history(u4) == [])

# ── 8. production isolation ────────────────────────────────────────────────
live = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", ".history.json")
live = os.path.abspath(live)
check("live .history.json untouched by tests", not os.path.exists(live))

print(f"\nround71: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
