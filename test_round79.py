"""Round-79 tests: official uploads outrank fan uploads.

Production case (2026-09-26): the song card for ADÉLA - "Nicole Kidman"
linked a fan-made color-coded lyrics video (Nickybors) instead of the
official AdelaMusicVEVO upload. Diagnosis:

1. The targeted official search already ran FIRST
   ("{artist} {song} official music video"), but YouTube returned the fan
   lyric video for it; it scored 110 on title match alone and the
   early-break (>= 50) stopped the search before the plain query ran.
2. The scorer gave no channel-authority bonus, so a VEVO upload titled
   plainly "Artist - Song" had no edge over a fan upload.

Fix, all in services/youtube_service.py:
- _is_official_channel(): one shared VEVO/*Official signal used by both
  the scorer and the kind classifier (they can't disagree anymore).
- _score_candidate(): +25 for official-channel uploads.
- _search_best(): the early break is kind-aware — only an official-kind
  winner stops the search; a lyric-kind winner lets the plain query run.
  Final selection prefers an official-kind candidate scoring >= 50 over a
  higher-scoring fan upload. Live winners are untouched (round-27).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _score_candidate, _is_official_channel, _classify_video_kind,
    get_youtube_link_info,
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


def _cand(vid, title, channel="SomeChannel"):
    return {'id': vid, 'title': title, 'channel': channel}


ARTIST, SONG = "ADÉLA", "Nicole Kidman"
Q1 = f"{ARTIST} {SONG} official music video"
Q2 = f"{ARTIST} {SONG}"

# The production fan upload (score 110 in the wild, kind lyric).
LYRIC_WIN = _cand(
    "txt21N-6wFM",
    "ADÉLA 'Nicole Kidman' Lyrics (Color Coded Lyrics) ENG",
    "Nickybors",
)
# The real official upload (raw 105 < lyric 110 — the exact trap).
VEVO_WIN = _cand("3sB4Iv_tM7U", "ADÉLA - Nicole Kidman", "AdelaMusicVEVO")
# Live winner for the round-27 contract check.
LIVE_WIN = _cand("live9", "ADÉLA - Nicole Kidman (Live at Coachella)",
                 "Coachella")


# ── 1. Official-channel signal ─────────────────────────────────────────────
check("vevo channel is official", _is_official_channel("AdelaMusicVEVO"))
check("'X Official' channel is official",
      _is_official_channel("Adela Official"))
check("fan channel is not official",
      not _is_official_channel("Nickybors"))
check("empty channel is not official", not _is_official_channel(""))


# ── 2. Scorer: VEVO boost ──────────────────────────────────────────────────
s_lyric = _score_candidate(LYRIC_WIN, ARTIST, SONG)
s_vevo = _score_candidate(VEVO_WIN, ARTIST, SONG)
check("lyric fan upload scores 110 (production value)", s_lyric == 110,
      f"got {s_lyric}")
check("vevo plain-title upload gets the channel boost",
      s_vevo == 105, f"got {s_vevo}")
check("boost never overrides the wrong-artist hard reject",
      _score_candidate(
          _cand("w1", "Marlon Craft - Lonely (Official Music Video)",
                "MarlonCraftVEVO"),
          "DallasK", "Lonely") == -100)


# ── 3. Production case: lyric wins q1, official surfaces on q2 ─────────────
get_youtube_link_info.cache_clear()
calls = []


def adela_fetch(q):
    calls.append(q)
    if q == Q1:
        return [LYRIC_WIN]
    if q == Q2:
        return [LYRIC_WIN, VEVO_WIN]
    return []


with patch.object(ys, '_fetch_candidates', side_effect=adela_fetch):
    info = get_youtube_link_info(ARTIST, SONG)
check("lyric-kind winner does NOT stop the search (both queries ran)",
      calls == [Q1, Q2], str(calls))
check("official upload wins despite lower raw score",
      info['url'] == "https://www.youtube.com/watch?v=3sB4Iv_tM7U",
      str(info))
check("winner labeled official", info['kind'] == 'official'
      and info['is_official'] and not info['is_live'], str(info))


# ── 4. No official anywhere: fan upload still served, honestly labeled ──────
get_youtube_link_info.cache_clear()


def lyric_only_fetch(q):
    return [LYRIC_WIN]


with patch.object(ys, '_fetch_candidates', side_effect=lyric_only_fetch):
    info2 = get_youtube_link_info(ARTIST, SONG)
check("lyric-only world: lyric video still returned",
      info2['url'] == "https://www.youtube.com/watch?v=txt21N-6wFM",
      str(info2))
check("lyric-only world: honestly labeled lyric",
      info2['kind'] == 'lyric' and not info2['is_official'], str(info2))


# ── 5. Official winner on q1: single search (fast path unchanged) ───────────
get_youtube_link_info.cache_clear()
calls5 = []


def official_first_fetch(q):
    calls5.append(q)
    return [VEVO_WIN]


with patch.object(ys, '_fetch_candidates', side_effect=official_first_fetch):
    info3 = get_youtube_link_info(ARTIST, SONG)
check("official winner: single search fired", calls5 == [Q1], str(calls5))
check("official winner: url + kind",
      info3['url'] == "https://www.youtube.com/watch?v=3sB4Iv_tM7U"
      and info3['kind'] == 'official', str(info3))


# ── 6. Round-27 contract: live winner never triggers the extra search ───────
get_youtube_link_info.cache_clear()
calls6 = []


def live_fetch(q):
    calls6.append(q)
    return [LIVE_WIN]


with patch.object(ys, '_fetch_candidates', side_effect=live_fetch):
    info4 = get_youtube_link_info(ARTIST, SONG)
check("live winner: no second query fired", calls6 == [Q1], str(calls6))
check("live winner: kept and labeled live",
      info4['url'] == "https://www.youtube.com/watch?v=live9"
      and info4['kind'] == 'live' and info4['is_live'], str(info4))


# ── 7. Classifier agrees with the scorer about official channels ───────────
c = _classify_video_kind("ADÉLA - Nicole Kidman", "AdelaMusicVEVO",
                         ARTIST, SONG)
check("vevo channel -> official kind", c['kind'] == 'official'
      and c['is_official'], str(c))
c2 = _classify_video_kind("ADÉLA 'Nicole Kidman' Lyrics", "Nickybors",
                          ARTIST, SONG)
check("fan lyric channel -> lyric kind", c2['kind'] == 'lyric'
      and not c2['is_official'], str(c2))


print(f"\nround79: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
