"""Round 42: /top de-noising + Last.fm label honesty.

- Per-song ↳ notes render only when they differ from the most common note
  (shared _dominant_note helper; ties break by first appearance).
- Last.fm fill note is 'Popular on Last.fm' (was 'Trending on Last.fm').
- Missing/blank note keys never crash the formatters.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import artist_service as AS

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


APPLE = 'Charting now on Apple Music'
LFM = 'Popular on Last.fm'


def _mk(note, n, start=0):
    return [{'artist': f'A{i}', 'song': f'S{i}', 'note': note}
            for i in range(start, start + n)]


# ── _dominant_note ──────────────────────────────────────────────────────
check("dominant: all-same", AS._dominant_note(_mk(APPLE, 7)) == APPLE)
check("dominant: 6-1 split", AS._dominant_note(_mk(APPLE, 6) + _mk(LFM, 1)) == APPLE)
check("dominant: 1-6 split", AS._dominant_note(_mk(LFM, 1) + _mk(APPLE, 6)) == APPLE)
check("dominant: tie -> first-seen wins",
      AS._dominant_note(_mk(APPLE, 1) + _mk(LFM, 1)) == APPLE
      and AS._dominant_note(_mk(LFM, 1) + _mk(APPLE, 1)) == LFM)
check("dominant: empty list", AS._dominant_note([]) == '')
check("dominant: missing note keys count as blank",
      AS._dominant_note([{'artist': 'A', 'song': 'S'}]) == '')
check("dominant: blank vs labeled",
      AS._dominant_note([{'artist': 'A', 'song': 'S'}, {'artist': 'B', 'song': 'T', 'note': LFM}]) == '')

# ── format_top_songs: the soul screenshot case ────────────────────────────
soul = _mk(APPLE, 6) + _mk(LFM, 1, start=6)
card = AS.format_top_songs('soul', soul)
check("top: 6-1 split renders exactly one sub-line", card.count('↳') == 1)
check("top: the exception keeps its note", f"↳ {LFM}" in card)
check("top: repeated note gone", f"↳ {APPLE}" not in card)
check("top: header still states both sources",
      "Sources: Apple Music Charts + Last.fm" in card)
check("top: rank order untouched",
      all(f"S{i}" in card for i in range(7)) and card.index("🥇") < card.index("7️⃣"))

check("top: all-same source -> zero sub-lines",
      '↳' not in AS.format_top_songs('pop', _mk(APPLE, 7)))
check("top: all-lastfm -> zero sub-lines, header covers it",
      '↳' not in AS.format_top_songs('pop', _mk(LFM, 7))
      and "Source: Last.fm" in AS.format_top_songs('pop', _mk(LFM, 7)))
check("top: songs without note key do not crash",
      '↳' not in AS.format_top_songs('pop', [{'artist': 'A', 'song': 'S'}]))

# ── format_trending shares the helper ─────────────────────────────────────
t = AS.format_trending([{'artist': 'A', 'song': 'S'}, {'artist': 'B', 'song': 'T'}], True)
check("trending: noteless output unchanged (no sub-lines)", '↳' not in t
      and "📈 Trending Now" in t)
t2 = AS.format_trending(
    [{'artist': 'A', 'song': 'S', 'note': APPLE},
     {'artist': 'B', 'song': 'T', 'note': 'Live debut'}], True)
check("trending: differing note renders, common one suppressed",
      t2.count('↳') == 1 and '↳ Live debut' in t2)

# ── Last.fm fill label ────────────────────────────────────────────────────
_tag = AS.LASTFM_GENRE_TAG.get('soul')
if _tag:
    AS._genre_tag_cache[_tag] = (time.time(), [{'artist': 'Sade', 'song': 'Like a Tattoo'}])
    filled = AS._get_lastfm_genre_songs('soul', limit=1)
    check("lastfm fill note says Popular (not Trending)",
          filled and filled[0]['note'] == 'Popular on Last.fm')
    check("old 'Trending on Last.fm' string is gone from the codebase",
          'Trending on Last.fm' not in open(
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'services', 'artist_service.py')).read())
else:
    print("SKIP: no Last.fm tag for soul")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
