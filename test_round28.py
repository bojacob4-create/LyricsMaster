"""Round-28 tests: clean song title for the video alt search.

Production bug (2026-09-24): tapping Video on "Brandi Carlile - Uninvited"
resolved the song to the live recording "Uninvited - Live at Newport Folk".
The round-27 alt search then asked YouTube for
"Uninvited - Live at Newport Folk official music video" AND required the full
polluted string to appear in each candidate's title — so Alanis Morissette's
official video could never match and no alternative was ever offered.
Round-27 tests only used the clean title "Uninvited", which is why they
passed while production failed.

Fix: _clean_song_title() strips recording qualifiers (live/festival/
acoustic/session-style markers) for the alt search only.  The primary
search keeps the full title — it is what finds the live video itself.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _clean_song_title, _find_official_alt, get_youtube_link_info,
    format_youtube_response,
)
import services.youtube_service as ys

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


# ── 1. _clean_song_title unit tests ─────────────────────────────────────────
check("trailing live segment dropped",
      _clean_song_title("Uninvited - Live at Newport Folk") == "Uninvited",
      repr(_clean_song_title("Uninvited - Live at Newport Folk")))
check("parenthetical live segment dropped",
      _clean_song_title("Hello (Live at the BRITs)") == "Hello",
      repr(_clean_song_title("Hello (Live at the BRITs)")))
check("bracket live segment dropped",
      _clean_song_title("Song [Live]") == "Song",
      repr(_clean_song_title("Song [Live]")))
check("trailing bare live dropped",
      _clean_song_title("The Story - Live") == "The Story",
      repr(_clean_song_title("The Story - Live")))
check("festival qualifier dropped",
      _clean_song_title("Halo - Newport Folk Festival") == "Halo",
      repr(_clean_song_title("Halo - Newport Folk Festival")))
check("clean title untouched",
      _clean_song_title("Water") == "Water")
check("non-live qualifier kept",
      _clean_song_title("Song - Studio Version") == "Song - Studio Version",
      repr(_clean_song_title("Song - Studio Version")))
check("empty stays empty", _clean_song_title("") == "")
check("acoustic live dropped",
      _clean_song_title("Skinny Love - Acoustic Live") == "Skinny Love",
      repr(_clean_song_title("Skinny Love - Acoustic Live")))


def _cand(vid, title, channel="SomeChannel"):
    return {'id': vid, 'title': title, 'channel': channel}


NEWPORT = _cand("brandi1",
               "Brandi Carlile - Uninvited (Newport Folk Fest 2026)",
               "Brandi Carlile")
ALANIS_OFFICIAL = _cand("alanis1",
                        "Alanis Morissette - Uninvited (Official Music Video)",
                        "AlanisMorissetteVEVO")


def _fetch_router(mapping):
    def fake(query):
        return mapping.get(query, mapping.get('*', []))
    return fake


# ── 2. The production bug: polluted song kills the alt search ───────────────
mapping_bug = {"Uninvited official music video": [ALANIS_OFFICIAL]}
with patch.object(ys, '_fetch_candidates',
                  side_effect=_fetch_router(mapping_bug)):
    polluted = _find_official_alt("Uninvited - Live at Newport Folk",
                                  "Brandi Carlile")
    clean = _find_official_alt("Uninvited", "Brandi Carlile")
check("polluted song string: alt never found (the production bug)",
      polluted is None, str(polluted))
check("clean song string: Alanis official video found",
      clean is not None and clean['url'] ==
      "https://www.youtube.com/watch?v=alanis1", str(clean))

# ── 3. End-to-end: the exact production call now yields the alt ──────────────
get_youtube_link_info.cache_clear()
mapping_e2e = {
    "Brandi Carlile Uninvited - Live at Newport Folk official music video":
        [NEWPORT],
    "Brandi Carlile Uninvited - Live at Newport Folk": [NEWPORT],
    "Uninvited official music video": [ALANIS_OFFICIAL],
}
with patch.object(ys, '_fetch_candidates',
                  side_effect=_fetch_router(mapping_e2e)):
    info = get_youtube_link_info("Brandi Carlile",
                                 "Uninvited - Live at Newport Folk")
check("e2e: winner is the live video",
      info['url'] == "https://www.youtube.com/watch?v=brandi1"
      and info['is_live'] and not info['is_official'], str(info))
check("e2e: alt official video found despite polluted input song",
      info['alt'] is not None and info['alt']['url'] ==
      "https://www.youtube.com/watch?v=alanis1", str(info.get('alt')))
check("e2e: clean_song exposed on the info dict",
      info.get('clean_song') == "Uninvited", str(info.get('clean_song')))

# ── 4. Response uses the clean title + the 2nd link ──────────────────────────
resp = format_youtube_response("Brandi Carlile",
                               "Uninvited - Live at Newport Folk",
                               info['url'], info)
check("response header shows the clean song title",
      "🎬 Brandi Carlile — Uninvited\n" in resp
      and "Live at Newport Folk" not in resp.split("🎥")[0], resp[:120])
check("response includes the 2nd (alternative) link",
      "🎬 Also: Alanis Morissette's official video:" in resp
      and "https://www.youtube.com/watch?v=alanis1" in resp, resp[:400])
check("response /lyrics hint uses the clean title",
      "🎤 /lyrics Brandi Carlile - Uninvited\n" in resp, resp[-120:])

# ── 5. Live winner, no alt anywhere: clean title, no Also block ──────────────
get_youtube_link_info.cache_clear()
with patch.object(ys, '_fetch_candidates',
                  side_effect=_fetch_router({'*': [NEWPORT]})):
    info2 = get_youtube_link_info("Brandi Carlile",
                                  "Uninvited - Live at Newport Folk")
resp2 = format_youtube_response("Brandi Carlile",
                                "Uninvited - Live at Newport Folk",
                                info2['url'], info2)
check("no alt: no 'Also' block, live note still shown",
      "🎬 Also:" not in resp2
      and "🎥 Live version — no official video found" in resp2, resp2[:200])
check("no alt: header still uses the clean title",
      "🎬 Brandi Carlile — Uninvited\n" in resp2, resp2[:120])

print(f"\nround28: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
