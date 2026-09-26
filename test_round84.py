"""Round-84 tests: /top dance (+ edm/electronic aliases).

User request (2026-09-26): /top listed 9 genres with electronic missing.
The live-charts layer already mapped dance/electronic -> Apple's 'Dance'
genre tag, but the /top path was double-gated: resolve_genre_key only
accepted GENRE_TOP_SONGS keys and _get_live_genre_songs needed an
APPLE_GENRE_MAP entry — neither had dance. Fix is config-level:
 1. 'dance' static pool in GENRE_TOP_SONGS (real English tracks).
 2. 'dance': ('us', 'Dance') in APPLE_GENRE_MAP.
 3. 'electronic'/'edm' -> 'dance' in GENRE_ALIASES.
 4. 🪩 emoji in format_top_songs; 'dance': '17' in APPLE_RSS_GENRE_ID.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services import artist_service as svc

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


# ── Alias resolution ────────────────────────────────────────────────
check("r84: 'dance' resolves", svc.resolve_genre_key('dance') == 'dance')
check("r84: 'Dance' resolves (case)", svc.resolve_genre_key('Dance') == 'dance')
check("r84: 'edm' alias", svc.resolve_genre_key('edm') == 'dance')
check("r84: 'EDM' alias (case)", svc.resolve_genre_key('EDM') == 'dance')
check("r84: 'electronic' alias", svc.resolve_genre_key('electronic') == 'dance')
check("r84: unknown genre still None", svc.resolve_genre_key('zydeco') is None)

# ── Available-genres listing ────────────────────────────────────────
genres = svc.get_available_genres()
check("r84: dance listed in available genres", 'dance' in genres, str(genres))
check("r84: still 10 genres total", len(genres) == 10, str(len(genres)))

# ── Live plumbing ───────────────────────────────────────────────────
check("r84: APPLE_GENRE_MAP has dance->Dance",
      svc.APPLE_GENRE_MAP.get('dance') == ('us', 'Dance'))
check("r84: APPLE_RSS_GENRE_ID has dance",
      svc.APPLE_RSS_GENRE_ID.get('dance') == '17')
check("r84: LASTFM_GENRE_TAG has dance (thin-slice top-up gate)",
      svc.LASTFM_GENRE_TAG.get('dance') == 'dance')
check("r84: static dance pool is English real tracks",
      len(svc.GENRE_TOP_SONGS.get('dance', [])) >= 5)

# get_top_by_genre with mocked live layer → serves dance, honors aliases.
live_songs = [{'artist': 'Dua Lipa', 'song': 'Houdini', 'note': 'Charting now on Apple Music'}]
with patch.object(svc, '_get_live_genre_songs', return_value=live_songs) as m:
    r1 = svc.get_top_by_genre('dance')
    r2 = svc.get_top_by_genre('edm')
    r3 = svc.get_top_by_genre('electronic')
check("r84: /top dance serves live songs",
      r1 is not None and r1[0] == 'dance' and r1[1] == live_songs)
check("r84: /top edm serves live songs",
      r2 is not None and r2[0] == 'dance' and r2[1] == live_songs)
check("r84: /top electronic serves live songs",
      r3 is not None and r3[0] == 'dance' and r3[1] == live_songs)
check("r84: live layer called with canonical key only",
      all(c.args[0] == 'dance' for c in m.call_args_list), str(m.call_args_list))

# All-live-sources-failed → None (honest charts-unreachable path).
with patch.object(svc, '_get_live_genre_songs', return_value=None):
    check("r84: dance with dead sources → None (honest, no static pool)",
          svc.get_top_by_genre('dance') is None)

# ── Formatting ──────────────────────────────────────────────────────
text = svc.format_top_songs('dance', live_songs)
check("r84: card title is 'Top Dance'", 'Top Dance' in text, text[:60])
check("r84: dance emoji 🪩", '🪩' in text, text[:60])

# ── Existing genres untouched ───────────────────────────────────────
check("r84: pop still resolves", svc.resolve_genre_key('pop') == 'pop')
check("r84: rnb/soul still share R&B/Soul",
      svc.APPLE_GENRE_MAP.get('rnb') == svc.APPLE_GENRE_MAP.get('soul') == ('us', 'R&B/Soul'))

print(f"\nround84: {passed} passed, {failed} failed")
