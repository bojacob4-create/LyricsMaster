"""Round-27 tests: video results are kind-aware (official/live/lyric/other).

The pipeline was match-and-present: the best artist+title overlap won and was
handed over as THE video.  When the only match was a live recording (covers,
concert-only songs…), the user got a live video passed off silently as the
video.  Now the winner is classified; a non-official live winner is labeled
honestly, and the original artist's official video is offered when one
surfaces (cover case: Brandi Carlile - Uninvited -> Alanis Morissette).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _classify_video_kind, get_youtube_link, get_youtube_link_info,
    format_youtube_response,
)
import services.youtube_service as ys
import handlers

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def cls(title, artist="", song="", channel=""):
    return _classify_video_kind(title, channel, artist, song)


# ── 1. Classifier ──────────────────────────────────────────────────────────
c = cls("Brandi Carlile - Uninvited (Newport Folk Fest 2026)",
        "Brandi Carlile", "Uninvited")
check("live festival video -> live", c['kind'] == 'live' and c['is_live']
      and not c['is_official'], str(c))

c = cls("Tyla - Water (Official Music Video)", "Tyla", "Water")
check("official music video -> official", c['kind'] == 'official'
      and c['is_official'] and not c['is_live'], str(c))

c = cls("Adele - Hello (Official Lyric Video)", "Adele", "Hello")
check("official lyric video -> official (no live note needed)",
      c['kind'] == 'official', str(c))

c = cls("Adele - Hello (Live at the BRIT Awards)", "Adele", "Hello")
check("'Live at ...' -> live", c['is_live'] and not c['is_official'], str(c))

c = cls("Tim McGraw - Live Like You Were Dying (Official Video)",
        "Tim McGraw", "Live Like You Were Dying")
check("song titled 'Live ...' does NOT false-positive as live",
      c['kind'] == 'official' and not c['is_live'], str(c))

c = cls("Live - Lightning Crashes (Official Video)",
        "Live", "Lightning Crashes")
check("band named 'Live' does NOT false-positive as live",
      c['kind'] == 'official' and not c['is_live'], str(c))

c = cls("Taylor Swift - All Too Well (Official Live Video)",
        "Taylor Swift", "All Too Well")
check("'Official Live Video' -> live + official (no 'not found' note)",
      c['is_live'] and c['is_official'], str(c))

c = cls("lofi hip hop radio - beats to relax/study to")
check("plain video -> other", c['kind'] == 'other', str(c))


def _cand(vid, title, channel="SomeChannel"):
    return {'id': vid, 'title': title, 'channel': channel}


LIVE_WIN = _cand("brandi1",
                "Brandi Carlile - Uninvited (Newport Folk Fest 2026)",
                "Newport Folk")
ALANIS_OFFICIAL = _cand("alanis1",
                        "Alanis Morissette - Uninvited (Official Music Video)",
                        "AlanisMorissetteVEVO")
OFFICIAL_WIN = _cand("tyla1", "Tyla - Water (Official Music Video)",
                     "TylaVEVO")


def _fetch_router(mapping):
    def fake(query):
        return mapping.get(query, mapping.get('*', []))
    return fake


# ── 2. Cover case: live winner + official video by another artist ──────────
get_youtube_link_info.cache_clear()
mapping = {
    "Brandi Carlile Uninvited official music video": [LIVE_WIN],
    "Uninvited official music video": [ALANIS_OFFICIAL],
}
with patch.object(ys, '_fetch_candidates', side_effect=_fetch_router(mapping)):
    info = get_youtube_link_info("Brandi Carlile", "Uninvited")
check("cover: winner flagged live/non-official",
      info['is_live'] and not info['is_official']
      and info['url'] == "https://www.youtube.com/watch?v=brandi1", str(info))
check("cover: alt official video offered",
      info['alt'] and info['alt']['url'] ==
      "https://www.youtube.com/watch?v=alanis1"
      and info['alt']['artist'] == "Alanis Morissette", str(info.get('alt')))

# ── 3. Live winner, no official alt anywhere -> alt None, still labeled ────
get_youtube_link_info.cache_clear()
with patch.object(ys, '_fetch_candidates',
                  side_effect=_fetch_router({'*': [LIVE_WIN]})):
    info2 = get_youtube_link_info("Brandi Carlile", "Uninvited")
check("live winner, no alt: alt is None",
      info2['is_live'] and info2['alt'] is None, str(info2))

# ── 4. Official winner -> untouched behavior, no alt search ────────────────
get_youtube_link_info.cache_clear()
calls = []
def counting_fetch(q):
    calls.append(q)
    return [OFFICIAL_WIN]
with patch.object(ys, '_fetch_candidates', side_effect=counting_fetch):
    info3 = get_youtube_link_info("Tyla", "Water")
check("official winner: kind official, no alt",
      info3['kind'] == 'official' and info3['alt'] is None, str(info3))
check("official winner: no second (alt) search fired", len(calls) == 1, str(calls))

# ── 5. Nothing scores -> search-fallback URL, kind none ────────────────────
get_youtube_link_info.cache_clear()
with patch.object(ys, '_fetch_candidates', return_value=[]):
    info4 = get_youtube_link_info("Nobody", "No Such Song xyz")
check("fallback: kind none + search URL",
      info4['kind'] == 'none' and 'results?search_query=' in info4['url'],
      str(info4))

# ── 6. Backward compat: string wrapper matches info url ────────────────────
get_youtube_link_info.cache_clear()
with patch.object(ys, '_fetch_candidates',
                  side_effect=_fetch_router({'*': [OFFICIAL_WIN]})):
    check("get_youtube_link still returns the URL string",
          get_youtube_link("Tyla", "Water") ==
          "https://www.youtube.com/watch?v=tyla1")

# ── 7. Response formatting ────────────────────────────────────────────────
official_info = {'url': 'https://www.youtube.com/watch?v=tyla1',
                 'kind': 'official', 'is_live': False, 'is_official': True,
                 'title': 'x', 'alt': None}
old_style = ("🎬 Tyla — Water\n"
             "━━━━━━━━━━━━━━━━━━━━━\n\n"
             "▶️ Watch now:\nhttps://www.youtube.com/watch?v=tyla1\n\n"
             "🎤 /lyrics Tyla - Water\n"
             "📊 /analyze Tyla - Water")
check("official: response byte-identical to the old format",
      format_youtube_response("Tyla", "Water",
                              "https://www.youtube.com/watch?v=tyla1",
                              official_info) == old_style)
check("no info: response byte-identical to the old format",
      format_youtube_response("Tyla", "Water",
                              "https://www.youtube.com/watch?v=tyla1") == old_style)

live_info = {'url': 'https://www.youtube.com/watch?v=brandi1',
             'kind': 'live', 'is_live': True, 'is_official': False,
             'title': 'x',
             'alt': {'url': 'https://www.youtube.com/watch?v=alanis1',
                     'artist': 'Alanis Morissette', 'title': 'y'}}
resp = format_youtube_response("Brandi Carlile", "Uninvited",
                               "https://www.youtube.com/watch?v=brandi1",
                               live_info)
check("live: labeled as live version", "🎥 Live version" in resp, resp[:60])
check("live: honest 'no official video' note",
      "no official video found" in resp, resp[:120])
check("live: alt official video offered",
      "Alanis Morissette" in resp
      and "https://www.youtube.com/watch?v=alanis1" in resp)

live_noalt = dict(live_info, alt=None)
resp2 = format_youtube_response("Brandi Carlile", "Uninvited",
                               "https://www.youtube.com/watch?v=brandi1",
                               live_noalt)
check("live without alt: no 'Also:' block", "Also:" not in resp2)

live_official = {'url': 'https://www.youtube.com/watch?v=t1', 'kind': 'live',
                 'is_live': True, 'is_official': True, 'title': 'x', 'alt': None}
resp3 = format_youtube_response("Taylor Swift", "All Too Well",
                               "https://www.youtube.com/watch?v=t1",
                               live_official)
check("official live: labeled, no 'not found' note",
      "🎥 Live version (official)" in resp3
      and "no official video found" not in resp3)

# ── 8. Card line helper ────────────────────────────────────────────────────
check("card line: live winner marked",
      handlers._yt_card_line(live_info, "fb") ==
      "🎬 https://www.youtube.com/watch?v=brandi1 — 🎥 live version")
check("card line: official winner plain",
      handlers._yt_card_line(official_info, "fb") ==
      "🎬 https://www.youtube.com/watch?v=tyla1")
check("card line: missing url -> fallback",
      handlers._yt_card_line(None, "fb") == "fb")
check("card line: official live not marked as live-only",
      handlers._yt_card_line(live_official, "fb") ==
      "🎬 https://www.youtube.com/watch?v=t1")

print(f"\nround27: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
