"""Round-20 tests: relevance floor for fuzzy lyrics search.

Tapping 'Chloe Flower - Song for Snow' (instrumental, no lyrics in the
database) used to open a dashboard for 'Miike Snow - Song For No One' —
a completely different recording accepted on a weak word overlap.
The fuzzy search now rejects results that don't plausibly match, so the
caller gets an honest 'not found' instead of a wrong song.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import lyrics_service as ls

passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok    {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {detail}")

floor = ls._meets_relevance_floor

# ── 1. floor unit tests ──────────────────────────────────────────────────
check("artist mismatch rejected",
      floor("chloe flower song for snow", "Chloe Flower",
            "Miike Snow", "Song For No One") is False)
check("exact match accepted",
      floor("taylor swift the fate of ophelia", "Taylor Swift",
            "Taylor Swift", "The Fate of Ophelia") is True)
check("single-word artist accepted",
      floor("tyla water", "Tyla", "Tyla", "Water") is True)
check("artist variant accepted (beatles)",
      floor("beatles yesterday", "Beatles",
            "The Beatles", "Yesterday") is True)
check("no-artist query uses title coverage",
      floor("water", "", "Tyla", "Water") is True)
check("no-artist query rejects unrelated",
      floor("water", "", "Adele", "Hello") is False)
check("wrong separator interpretation rejected",
      floor("love kendrick", "love", "Kendrick Lamar", "LOVE.") is False)
check("right separator interpretation accepted",
      floor("kendrick love", "kendrick", "Kendrick Lamar", "LOVE.") is True)
check("feat. artist accepted",
      floor("tyla water", "Tyla", "Tyla feat. Travis Scott", "Water") is True)
check("empty query rejected",
      floor("", "", "Nobody", "Nothing") is False)

# ── 2. _fetch_from_lrclib_search with mocked HTTP ────────────────────────
class FakeResp:
    status_code = 200
    def __init__(self, results):
        self._results = results
    def json(self):
        return self._results  # real lrclib search API returns a bare list

LYRICS = "la la la " * 20  # > 30 chars

MIIKE = [{"artistName": "Miike Snow", "trackName": "Song For No One",
          "plainLyrics": LYRICS}]
TAYLOR = [{"artistName": "Taylor Swift", "trackName": "The Fate of Ophelia",
           "plainLyrics": LYRICS}]

with patch.object(ls.session, "get", return_value=FakeResp(MIIKE)):
    check("weak fuzzy hit -> None (no wrong song)",
          ls._fetch_from_lrclib_search("chloe flower song for snow",
                                       expected_artist="Chloe Flower") is None)

with patch.object(ls.session, "get", return_value=FakeResp(TAYLOR)):
    r = ls._fetch_from_lrclib_search("taylor swift the fate of ophelia",
                                    expected_artist="Taylor Swift")
    check("strong fuzzy hit still returned",
          r is not None and r[0] == "Taylor Swift"
          and r[1] == "The Fate of Ophelia", repr(r))

# ── 3. end-to-end through search_song_info ───────────────────────────────
with patch.object(ls, "_fetch_from_lrclib_direct", return_value=None), \
     patch.object(ls.session, "get", return_value=FakeResp(MIIKE)):
    check("search_song_info rejects weak match",
          ls.search_song_info("Chloe Flower", "Song for Snow") is None)

with patch.object(ls, "_fetch_from_lrclib_direct", return_value=None), \
     patch.object(ls.session, "get", return_value=FakeResp(TAYLOR)):
    r = ls.search_song_info("Taylor Swift", "The Fate of Ophelia")
    check("search_song_info keeps strong match",
          r is not None and r[0] == "Taylor Swift", repr(r))

# direct exact lookups are untouched by the floor
DIRECT = {"artistName": "Chloe Flower", "trackName": "Song for Snow",
          "plainLyrics": LYRICS}
class FakeDirectResp:
    status_code = 200
    def json(self):
        return DIRECT
with patch.object(ls.session, "get", return_value=FakeDirectResp()):
    r = ls._fetch_from_lrclib_direct("Chloe Flower", "Song for Snow")
    check("direct exact lookup unaffected",
          r is not None and r[0] == "Chloe Flower", repr(r))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
