"""Round-28 tests (revised): no second link; clean song title for display.

History:
- Round-27 added an "alternative" official video by another artist when the
  winner was a non-official live performance.
- Round-28's first attempt kept the mechanism but fixed its query pollution
  (the song string arrived carrying the live recording's qualifier, e.g.
  "Uninvited - Live at Newport Folk", which the alt search could never
  match).
- Production then proved the deeper problem: a title-only search cannot
  reliably establish that another artist's same-titled song is the
  covered/original work.  It surfaced Haven Lough & Gibson Ardoline's
  unrelated "UNINVITED" as the "official video" for Brandi Carlile's
  Alanis cover.  A wrong second link is worse than no second link.

Current behavior: the alternative search is gone entirely.  A non-official
live winner gets the honest "Live version — no official video found" note
and nothing else.  _clean_song_title() remains, but only for display: the
response header and /lyrics hint show the clean song title instead of the
polluted recording qualifier.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _clean_song_title, get_youtube_link_info, format_youtube_response,
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
# The unrelated same-titled song YouTube actually surfaced in production.
HAVEN = _cand("haven1",
              "Haven Lough & Gibson Ardoline - UNINVITED (Official Music Video)",
              "HavenLoughVEVO")


def _fetch_router(mapping):
    def fake(query):
        return mapping.get(query, mapping.get('*', []))
    return fake


# ── 2. E2E: the exact production call yields NO second link ─────────────────
get_youtube_link_info.cache_clear()
calls = []
def recording_fetch(query):
    calls.append(query)
    return {"Uninvited official music video": [HAVEN],
            "Brandi Carlile Uninvited - Live at Newport Folk official music video":
                [NEWPORT],
            "Brandi Carlile Uninvited - Live at Newport Folk": [NEWPORT]}.get(query, [])
with patch.object(ys, '_fetch_candidates', side_effect=recording_fetch):
    info = get_youtube_link_info("Brandi Carlile",
                                 "Uninvited - Live at Newport Folk")
check("e2e: winner is the live video",
      info['url'] == "https://www.youtube.com/watch?v=brandi1"
      and info['is_live'] and not info['is_official'], str(info))
check("e2e: info dict carries no 'alt' at all", 'alt' not in info, str(info))
check("e2e: clean_song exposed on the info dict",
      info.get('clean_song') == "Uninvited", str(info.get('clean_song')))
check("e2e: no title-only alt search fired",
      all(q != "Uninvited official music video" for q in calls), str(calls))

# ── 3. Response: honest live note, clean title, NEVER a second link ─────────
resp = format_youtube_response("Brandi Carlile",
                               "Uninvited - Live at Newport Folk",
                               info['url'], info)
check("response header shows the clean song title",
      "🎬 Brandi Carlile — Uninvited\n" in resp
      and "Live at Newport Folk" not in resp.split("🎥")[0], resp[:120])
check("response: no 'Also' block, even with an alt-shaped candidate around",
      "🎬 Also:" not in resp, resp[:400])
check("response: live note still shown",
      "🎥 Live version — no official video found" in resp, resp[:200])
check("response /lyrics hint uses the clean title",
      "🎤 /lyrics Brandi Carlile - Uninvited\n" in resp, resp[-120:])

# ── 4. An info dict WITH a stale alt key is ignored, not rendered ────────────
stale = dict(info, alt={'url': 'https://www.youtube.com/watch?v=haven1',
                        'artist': 'Haven Lough', 'title': 'x'})
resp2 = format_youtube_response("Brandi Carlile",
                                "Uninvited - Live at Newport Folk",
                                info['url'], stale)
check("stale alt key in info: still no 'Also' block",
      "🎬 Also:" not in resp2 and "haven1" not in resp2, resp2[:300])

# ── 5. Official winner: untouched, still no second link machinery ────────────
get_youtube_link_info.cache_clear()
official = _cand("tyla1", "Tyla - Water (Official Music Video)", "TylaVEVO")
calls2 = []
def counting_fetch(q):
    calls2.append(q)
    return [official]
with patch.object(ys, '_fetch_candidates', side_effect=counting_fetch):
    info3 = get_youtube_link_info("Tyla", "Water")
check("official winner: no 'alt' key on the info dict",
      info3['kind'] == 'official' and 'alt' not in info3, str(info3))
check("official winner: single primary search only",
      len(calls2) == 1, str(calls2))

print(f"\nround28: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
