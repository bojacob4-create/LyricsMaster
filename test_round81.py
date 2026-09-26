"""Round-81 tests: song-overlap guard — a video that never mentions the
song can never be the song's video.

Production case (2026-09-26): the "Taylor Swift - Wi$h Li$t" song card
linked "Taylor Swift - Elizabeth Taylor (Official Music Video)" — a
different song. It scored 75 on artist-in-title (+30) + artist-in-channel
(+20) + "official music video" text (+25) with ZERO song-title overlap.
The round-43 hard reject only fires on a different ARTIST credit; here
the artist was right, so nothing stopped it.

Fix:
- services/youtube_service.py::_score_candidate(): hard reject (-100,
  mirroring round-43) when the normalized song title is absent from the
  normalized video title. Skipped when no song name was given. If every
  candidate is rejected, the card falls back to an honest YouTube search
  link instead of a wrong video.
- services/youtube_downloader_service.py::_score_candidate(): same guard
  for the MP3 path (zero song-token overlap → -1e9); artist-only
  requests (no song named) keep soft scoring.
- Both normalizers map stylized swaps ($→s, @→a) before stripping, so
  "Wi$h Li$t" and "Wish List" are the same song — the guard can't
  false-reject a video that spells the title differently. Digits stay
  digits ("7 Years" must not become "t years").

Net on the production case: "Elizabeth Taylor" is rejected, the
"official music video" query's winner collapses, the plain query runs,
and the 17M-view official lyric video wins — labeled honestly as a
lyric video.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _normalize, _score_candidate, get_youtube_link_info,
)
import services.youtube_service as ys
from services.youtube_downloader_service import (
    _score_candidate as _dl_score, _norm_key_text,
)

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


ARTIST, SONG = "Taylor Swift", "Wi$h Li$t"
ELIZABETH = _cand(
    "WqbJT_vC0rs",
    "Taylor Swift - Elizabeth Taylor (Official Music Video)",
    "Taylor Swift",
)
LYRIC_OFFICIAL = _cand(
    "wqgUzLHgNMI",
    "Taylor Swift - Wi$h Li$t (Lyric Video)",
    "Taylor Swift",
)


# ── 1. Normalizer: stylized swaps ──────────────────────────────────────────
check("normalizer maps $ to s", _normalize("Wi$h Li$t") == "wish list",
      repr(_normalize("Wi$h Li$t")))
check("normalizer maps @ to a", _normalize("M@tt Healy") == "matt healy",
      repr(_normalize("M@tt Healy")))
check("normalizer leaves digits alone", _normalize("7 Years") == "7 years",
      repr(_normalize("7 Years")))
check("downloader normalizer agrees",
      _norm_key_text("Wi$h Li$t") == "wish list",
      repr(_norm_key_text("Wi$h Li$t")))


# ── 2. Watch-link scorer: zero song overlap → hard reject ─────────────────
s = _score_candidate(ELIZABETH, ARTIST, SONG)
check("wrong song with right artist is hard-rejected", s == -100,
      f"got {s}")
check("official lyric video of the right song passes",
      _score_candidate(LYRIC_OFFICIAL, ARTIST, SONG) == 100,
      str(_score_candidate(LYRIC_OFFICIAL, ARTIST, SONG)))
check("plain-spelling fan video is NOT false-rejected",
      _score_candidate(_cand("f1", "Taylor Swift - Wish List (Lyrics)",
                             "FanChannel"), ARTIST, SONG) > 0)
check("live version of the right song still passes",
      _score_candidate(_cand("l1", "Adele - Hello (Live at Glastonbury)",
                             "AdeleVEVO"), "Adele", "Hello") > 0)
check("guard skipped when no song name given",
      _score_candidate(_cand("x1", "Tyla - Water", "TylaVEVO"),
                       "Tyla", "") > 0)


# ── 3. Full pipeline: production scenario end to end ───────────────────────
get_youtube_link_info.cache_clear()


def fetch(q):
    # q1 ("official music video" query) only surfaces the wrong song;
    # q2 (plain query) surfaces the true official lyric video.
    if "official music video" in q:
        return [ELIZABETH]
    return [ELIZABETH, LYRIC_OFFICIAL]


with patch.object(ys, '_fetch_candidates', side_effect=fetch):
    info = get_youtube_link_info(ARTIST, SONG)
check("pipeline winner is the official lyric video",
      info['url'] == "https://www.youtube.com/watch?v=wqgUzLHgNMI",
      str(info))
check("winner honestly labeled lyric",
      info['kind'] == 'lyric' and not info['is_official'], str(info))


# ── 4. Pipeline: all candidates rejected → honest search fallback ─────────
get_youtube_link_info.cache_clear()
with patch.object(ys, '_fetch_candidates', return_value=[ELIZABETH]):
    info = get_youtube_link_info(ARTIST, SONG)
check("total rejection falls back to a search link, not a wrong video",
      info['url'].startswith("https://www.youtube.com/results"),
      str(info))


# ── 5. Downloader scorer: same guard ───────────────────────────────────────
check("downloader rejects zero-overlap track",
      _dl_score(ELIZABETH['title'], ELIZABETH['channel'], 229,
                ARTIST, SONG, 229) == -1e9)
check("downloader keeps the true lyric video",
      _dl_score(LYRIC_OFFICIAL['title'], LYRIC_OFFICIAL['channel'], 229,
                ARTIST, SONG, 229) > 0)
check("downloader artist-only request keeps soft scoring",
      _dl_score("Taylor Swift - 1989 Mix", "DJ", 3600,
                "Taylor Swift", "", None) > 0)


print(f"\nround81: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
