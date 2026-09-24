"""Round-18 tests: mood mix lines show each song's duration.

_send_mood_mix appends a verified '⏱️ m:ss' suffix per song. Durations
come from parallel iTunes Search lookups; a hit is only accepted when its
artist+track tokens solidly overlap the query (no wrong-song durations).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers as h

passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok    {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {detail}")

# ── 1. duration formatting ───────────────────────────────────────────────
check("fmt 142000ms -> 2:22", h._format_duration_ms(142000) == "2:22")
check("fmt 65000ms -> 1:05", h._format_duration_ms(65000) == "1:05")
check("fmt 396000ms -> 6:36", h._format_duration_ms(396000) == "6:36")
check("fmt 0ms -> 0:00", h._format_duration_ms(0) == "0:00")
check("fmt rounds to nearest second", h._format_duration_ms(134600) == "2:15")

# ── 2. _itunes_duration with mocked HTTP ─────────────────────────────────
class FakeResp:
    def __init__(self, results):
        self._results = results
    def json(self):
        return {"results": self._results}

GOOD = [{"artistName": "Chloe Flower", "trackName": "Song for Snow",
         "trackTimeMillis": 134000}]

with patch.object(h.requests, "get",
                  return_value=FakeResp(GOOD)):
    check("verified hit returns duration",
          h._itunes_duration("Chloe Flower", "Song for Snow") == "2:14")

# Wrong song by a similar artist must not donate its duration
WRONG = [{"artistName": "Miike Snow", "trackName": "Song For No One",
          "trackTimeMillis": 200000}]
with patch.object(h.requests, "get",
                  return_value=FakeResp(WRONG)):
    check("wrong-song hit rejected",
          h._itunes_duration(
              "Chloe Flower, Academy of St Martin in the Fields",
              "Song for Snow") is None)

with patch.object(h.requests, "get", return_value=FakeResp([])):
    check("no results -> None",
          h._itunes_duration("Nobody", "Nothing") is None)

with patch.object(h.requests, "get", side_effect=TimeoutError):
    check("http error -> None (never raises)",
          h._itunes_duration("A", "B") is None)

# hit without trackTimeMillis is unusable
with patch.object(h.requests, "get",
                  return_value=FakeResp(
                      [{"artistName": "A", "trackName": "B"}])):
    check("hit without duration -> None",
          h._itunes_duration("A", "B") is None)

# ── 3. _fetch_mix_durations ─────────────────────────────────────────────
songs = [{"artist": "A1", "name": "S1", "source": "fresh"},
         {"artist": "A2", "name": "S2", "source": "fresh"}]
with patch.object(h, "_itunes_duration", side_effect=["2:14", None]):
    durs = h._fetch_mix_durations(songs)
check("parallel fetch keeps order, one entry per song",
      durs == ["2:14", None], repr(durs))

with patch.object(h, "_itunes_duration", side_effect=RuntimeError("boom")):
    check("fetch never raises",
          h._fetch_mix_durations(songs) == [None, None])

# ── 4. _send_mood_mix renders durations in the user-visible text ─────────
captured = {}

class FakeChat:
    def send_action(self, action=None):
        pass

class FakeMessage:
    chat = FakeChat()
    def reply_text(self, text, **kw):
        captured["text"] = text
        captured["kw"] = kw

class FakeUpdate:
    message = FakeMessage()

mix = [{"artist": "Chloe Flower", "name": "Song for Snow", "source": "fresh"},
       {"artist": "No Hit Band", "name": "Unknown Track", "source": "fresh"}]

with patch.object(h, "get_mood_mix", return_value=mix), \
     patch.object(h, "_fetch_mix_durations", return_value=["2:14", None]), \
     patch.object(h, "song_list_buttons", return_value=None), \
     patch.object(h, "log_interaction", return_value=None):
    h._send_mood_mix(FakeUpdate(), 123, "focus")

text = captured.get("text", "")
check("duration shown on verified line",
      "1. 🆕 Chloe Flower — Song for Snow ⏱️ 2:14" in text, text[:200])
check("no suffix when lookup missed",
      "2. 🆕 No Hit Band — Unknown Track\n" in text or
      text.rstrip().endswith("Unknown Track"), text[-120:])
check("header/footer untouched",
      "Focus Mix" in text and "/mood" in text)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
