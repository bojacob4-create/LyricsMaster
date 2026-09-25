"""Round 43: YouTube wrong-artist hard reject + no-lyrics honesty.

- services.youtube_service._title_credits_other_artist: a video title that
  explicitly credits a DIFFERENT artist ('Marlon Craft - Lonely' for a
  STARGUIDE & DallasK query) is never our video.  Fires only on explicit
  attribution structure ('A - T', 'T - A', 'T by A'); attribution-free
  titles ('Lonely (Official Music Video)') are untouched.
- Both YouTube scorers (watch-link + MP3 downloader) hard-reject such
  candidates via the one shared helper.
- The no-lyrics card no longer claims 'instrumental track' (a guess);
  it honestly says no lyrics were found.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_service import (
    _score_candidate as _watch_score,
    _title_credits_other_artist,
    _search_best,
)
import services.youtube_service as YTS
from services.youtube_downloader_service import _score_candidate as _dl_score
import handlers
from handlers import _no_lyrics_card_text

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


A = 'STARGUIDE & DallasK'
S = 'Lonely'
WRONG = {'title': 'Marlon Craft - Lonely (Official Music Video)',
         'channel': 'MarlonCraft', 'id': 'GceApY_-qww'}
RIGHT = {'title': 'STARGUIDE & DallasK - Lonely (Official Audio)',
         'channel': 'STARGUIDE', 'id': 'abc123'}
BARE = {'title': 'Lonely (Official Music Video)',
        'channel': 'STARGUIDE', 'id': 'def456'}

# ── _title_credits_other_artist ─────────────────────────────────────────
check("conflict detected: 'Marlon Craft - Lonely' vs STARGUIDE",
      _title_credits_other_artist(WRONG['title'], A, S) is True)
check("correct attribution not flagged",
      _title_credits_other_artist(RIGHT['title'], A, S) is False)
check("no attribution structure never fires",
      _title_credits_other_artist(BARE['title'], A, S) is False)
check("reversed 'Title - Artist' with OUR artist is fine",
      _title_credits_other_artist('Lonely - STARGUIDE & DallasK (Lyric Video)', A, S) is False)
check("reversed 'Title - Artist' with WRONG artist fires",
      _title_credits_other_artist('Lonely - Marlon Craft', A, S) is True)
check("partial artist overlap is fine ('STARGUIDE - Lonely')",
      _title_credits_other_artist('STARGUIDE - Lonely', A, S) is False)
check("'Title by WRONG artist' fires",
      _title_credits_other_artist('Lonely by Marlon Craft', A, S) is True)
check("'Title by OUR artist' is fine",
      _title_credits_other_artist('Lonely by STARGUIDE', A, S) is False)
check("pipe separator conflict fires",
      _title_credits_other_artist('Marlon Craft | Lonely (Official Audio)', A, S) is True)
check("pipe separator agreement is fine",
      _title_credits_other_artist('STARGUIDE & DallasK | Lonely', A, S) is False)
check("round-13c regression: 'Twins React to ADELA - ...' keeps ADELA credit",
      _title_credits_other_artist(
          'Twins React to ADÉLA - Nicole Kidman (Official Music Video)',
          'ADÉLA', 'Nicole Kidman') is False)
check("compilation head rejected ('Top 50 Lonely Songs - Billboard')",
      _title_credits_other_artist('Top 50 Lonely Songs - Billboard', A, S) is True)
check("empty artist never rejects",
      _title_credits_other_artist(WRONG['title'], '', S) is False)
check("case-insensitive ('marlon craft - lonely')",
      _title_credits_other_artist('marlon craft - lonely', A, S) is True)

# ── watch-link scorer ───────────────────────────────────────────────────
check("watch scorer hard-rejects wrong-artist video",
      _watch_score(WRONG, A, S) < 20)
check("watch scorer still accepts correct video (>=50)",
      _watch_score(RIGHT, A, S) >= 50)
check("watch scorer still accepts attribution-free title",
      _watch_score(BARE, A, S) >= 50)

# ── _search_best: wrong artist can no longer win ────────────────────────
_orig = YTS._fetch_candidates
YTS._fetch_candidates = lambda q: [WRONG, RIGHT]
try:
    best, score, _seen = _search_best(A, S, ['STARGUIDE DallasK Lonely'])
    check("search_best picks the RIGHT video, not the wrong artist",
          best is not None and best['id'] == 'abc123')
finally:
    YTS._fetch_candidates = _orig

YTS._fetch_candidates = lambda q: [WRONG]
try:
    best, score, _seen = _search_best(A, S, ['STARGUIDE DallasK Lonely'])
    check("search_best returns None when only wrong-artist videos exist",
          best is None)
finally:
    YTS._fetch_candidates = _orig

# ── MP3 downloader scorer ───────────────────────────────────────────────
check("downloader hard-rejects wrong-artist video",
      _dl_score(WRONG['title'], WRONG['channel'], 200, A, S, 200) < -1e8)
check("downloader still scores correct video positively",
      _dl_score(RIGHT['title'], RIGHT['channel'], 200, A, S, 200) > 0)
check("downloader still scores attribution-free title positively",
      _dl_score(BARE['title'], BARE['channel'], 200, A, S, 200) > 0)

# ── no-lyrics card honesty ──────────────────────────────────────────────
t = _no_lyrics_card_text('STARGUIDE & DallasK', 'Lonely', 'Dance', '001', 'sad')
check("card no longer claims 'instrumental'",
      'instrumental' not in t.lower())
check("card honestly says no lyrics found",
      'No lyrics found' in t)
check("card keeps artist/title/genre/album",
      'STARGUIDE & DallasK' in t and 'Lonely' in t and 'Dance' in t)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
