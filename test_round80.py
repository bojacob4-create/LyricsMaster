"""Round-80 tests: reaction videos can never masquerade as official.

Production follow-up (2026-09-26): after round-79, the ADÉLA song card
linked "Twins React to ADÉLA - Nicole Kidman (Official Music Video)" —
a REACTION video. Its title mentions the official video only because it
is reacting TO it, but:
  1. the kind classifier substring-matched 'official music video' and
     labeled it official, and
  2. the scorer gave it the +25 official-title bonus; the -50 reaction
     penalty left it at 55, still above the 50 bar — so round-79's
     official-preference picked it as the "official" winner.

Fix, all in services/youtube_service.py:
- _REACTION_PHRASES: one shared phrase list ('react to', 'reacts to',
  'reaction to', 'reacting to') — phrases, not bare 'react', so a song
  genuinely titled "React" stays safe.
- _score_candidate(): a reaction-phrase title never earns the
  official-text bonus (the -50 penalty still applies).
- _classify_video_kind(): a reaction-phrase title is never official.

Net effect on the production case: the reaction video scores 30 (below
the bar) and classifies as 'other'; the card falls back to the lyric
video, honestly labeled, until YouTube's index ranks the real VEVO
upload. Genuine official uploads are untouched.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _score_candidate, _classify_video_kind, get_youtube_link_info,
    _REACTION_PHRASES,
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

# The production reaction video (was: score 55, kind official).
REACT_WIN = _cand(
    "TEUhW2cqgAA",
    "Twins React to ADÉLA - Nicole Kidman (Official Music Video)",
    "TWINTUBE",
)
LYRIC_WIN = _cand(
    "txt21N-6wFM",
    "ADÉLA 'Nicole Kidman' Lyrics (Color Coded Lyrics) ENG",
    "Nickybors",
)


# ── 1. The reaction video: no bonus, below the bar, never official ─────────
s = _score_candidate(REACT_WIN, ARTIST, SONG)
check("reaction video scores 30 (no official bonus, below the 50 bar)",
      s == 30, f"got {s}")
c = _classify_video_kind(REACT_WIN['title'], REACT_WIN['channel'],
                         ARTIST, SONG)
check("reaction video never classifies as official",
      not c['is_official'] and c['kind'] != 'official', str(c))


# ── 2. Production pipeline: reaction video can no longer win ────────────────
get_youtube_link_info.cache_clear()
calls = []


def adela_fetch(q):
    calls.append(q)
    return [LYRIC_WIN, REACT_WIN]


with patch.object(ys, '_fetch_candidates', side_effect=adela_fetch):
    info = get_youtube_link_info(ARTIST, SONG)
check("reaction video is not the winner",
      info['url'] == "https://www.youtube.com/watch?v=txt21N-6wFM",
      str(info))
check("winner honestly labeled lyric",
      info['kind'] == 'lyric' and not info['is_official'], str(info))


# ── 3. Genuine official uploads are untouched ───────────────────────────────
off = _cand("t1", "Tyla - Water (Official Music Video)", "TylaVEVO")
check("genuine official keeps its title bonus",
      _score_candidate(off, "Tyla", "Water") == 150,
      str(_score_candidate(off, "Tyla", "Water")))
check("genuine official still classifies official",
      _classify_video_kind(off['title'], off['channel'],
                           "Tyla", "Water")['kind'] == 'official')


# ── 4. A song genuinely titled "React" stays safe ───────────────────────────
songreact = _cand("r1", "The React - React (Official Music Video)",
                  "TheReactVEVO")
check("song titled 'React' is not treated as a reaction video",
      _classify_video_kind(songreact['title'], songreact['channel'],
                           "The React", "React")['kind'] == 'official')
check("song titled 'React' keeps its official bonus",
      _score_candidate(songreact, "The React", "React") == 130)


# ── 5. The phrase list is the single source of truth ────────────────────────
check("reaction phrases cover the known phrasings",
      set(_REACTION_PHRASES) >=
      {'react to', 'reacts to', 'reaction to', 'reacting to'})


print(f"\nround80: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
