"""Round-21 tests: no-lyrics fallback card.

Tapping a mix song with no lyrics anywhere (instrumentals, house, …)
used to end in "Couldn't find that song." even though the track is real.
Now the bot verifies the track via iTunes/YouTube and shows a graceful
card — video, MP3, artist profile, lyrics-free similar songs, wiki —
instead of a dead end.  Garbage queries still get the classic not-found.
"""
import os
import sys
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import buttons
import handlers
from handlers import (
    _no_lyrics_card_text, _itunes_track_lookup, _verify_track_exists,
    _pop_no_lyrics_ctx, _NO_LYRICS_CTX,
)
from input_parser import parse_song_query

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _cb_actions(markup):
    out = []
    for row in markup.inline_keyboard:
        for b in row:
            out.append((b.text, (b.callback_data or '').split(':')[0]))
    return out


# ── 1. Card text ──────────────────────────────────────────────────────────
t = _no_lyrics_card_text('Chloe Flower', 'Song for Snow', 'Classical', 'Candid', 'focus')
check("card: title line", "🎵 *Song for Snow*" in t)
check("card: artist line", "👤 Chloe Flower" in t)
check("card: no-lyrics note", "No lyrics found for this track" in t)  # round-43: honest, not "instrumental"
check("card: album line", "💿 Album: Candid" in t)
check("card: genre line", "🎭 Genre: Classical" in t)
check("card: mood line", "Spotted in your" in t and "Focus Mix" in t)
check("card: no Quick Stats", "Quick Stats" not in t and "Words:" not in t)

t2 = _no_lyrics_card_text('DJ X', 'Untitled Groove', '', '', None)
check("card minimal: no empty album/genre lines",
      "Album:" not in t2 and "Genre:" not in t2 and "Spotted in your" not in t2)
check("card minimal: no lyrics/analyze hints",
      "Lyrics" not in t2.split("🎼")[0] and "Analyze" not in t2)

t3 = _no_lyrics_card_text('A * B', 'C_D', '', '', None)
check("card: markdown escaped", "A \\* B" in t3 and "C\\_D" in t3)

# ── 2. Card buttons ───────────────────────────────────────────────────────
acts = _cb_actions(buttons.no_lyrics_card_buttons('Chloe Flower', 'Song for Snow'))
kinds = [a for _, a in acts]
check("card buttons: 5 buttons", len(acts) == 5, str(acts))
check("card buttons: rows 2/2/1",
      [len(r) for r in buttons.no_lyrics_card_buttons('A', 'B').inline_keyboard] == [2, 2, 1])
for need in ('youtube', 'mp3', 'artist', 'similar_nl', 'wiki'):
    check(f"card buttons: has {need}", need in kinds, str(kinds))
check("card buttons: no lyrics/analyze/translate",
      not ({'lyrics', 'analyze', 'translate'} & set(kinds)))
artist_btn = [b for b in buttons.no_lyrics_card_buttons('Chloe Flower', 'Song for Snow').inline_keyboard[1] if b.text == '👤 Artist Profile'][0]
check("card buttons: artist btn carries artist only",
      artist_btn.callback_data == 'artist:Chloe Flower', artist_btn.callback_data)
wiki_btn = buttons.no_lyrics_card_buttons('Chloe Flower', 'Song for Snow').inline_keyboard[2][0]
check("card buttons: wiki btn carries artist",
      wiki_btn.callback_data == 'wiki:Chloe Flower', wiki_btn.callback_data)

# ── 3. Similar-view buttons ───────────────────────────────────────────────
recs = [{'artist': 'Ludovico Einaudi', 'name': 'Nuvole Bianche'},
        {'artist': 'Max Richter', 'name': 'On the Nature of Daylight'}]
sacts = _cb_actions(buttons.no_lyrics_similar_buttons('Chloe Flower - Song for Snow', recs))
skinds = [a for _, a in sacts]
check("similar buttons: no lyrics/analyze for source",
      'lyrics' not in skinds and 'analyze' not in skinds, str(skinds))
check("similar buttons: similar_more_nl present", 'similar_more_nl' in skinds, str(skinds))
check("similar buttons: rec song buttons",
      sum(1 for _, a in sacts if a == 'song') == 2, str(sacts))
sacts0 = _cb_actions(buttons.no_lyrics_similar_buttons('A - B', []))
check("similar buttons: empty recs still has more",
      'similar_more_nl' in [a for _, a in sacts0])

# ── 4. iTunes lookup scoring (mocked) ─────────────────────────────────────
def _resp(results):
    m = MagicMock()
    m.json.return_value = {'results': results}
    return m


good = [{'artistName': 'Chloe Flower', 'trackName': 'Song for Snow',
         'artworkUrl100': 'https://x/100x100.jpg',
         'primaryGenreName': 'Classical', 'collectionName': 'Candid'}]
with patch('handlers.requests.get', return_value=_resp(good)):
    hit = _itunes_track_lookup('Chloe Flower', 'Song for Snow')
check("itunes: solid hit accepted", hit and hit['artist'] == 'Chloe Flower', str(hit))
check("itunes: artwork upgraded", hit and hit['artwork'] == 'https://x/600x600.jpg',
      str(hit and hit['artwork']))
check("itunes: genre/album kept",
      hit and hit['genre'] == 'Classical' and hit['album'] == 'Candid')

weak = [{'artistName': 'Miike Snow', 'trackName': 'Song For No One',
         'artworkUrl100': 'https://x/100x100.jpg',
         'primaryGenreName': 'Pop', 'collectionName': 'Y'}]
with patch('handlers.requests.get', return_value=_resp(weak)):
    hit2 = _itunes_track_lookup('Chloe Flower', 'Song for Snow')
check("itunes: wrong-artist hit rejected", hit2 is None, str(hit2))

with patch('handlers.requests.get', return_value=_resp([])):
    check("itunes: empty results -> None", _itunes_track_lookup('A', 'B') is None)
with patch('handlers.requests.get', side_effect=Exception("down")):
    check("itunes: network error -> None", _itunes_track_lookup('A', 'B') is None)

# ── 5. Track verification ─────────────────────────────────────────────────
with patch('handlers._itunes_track_lookup', return_value={'artist': 'A', 'title': 'B'}), \
     patch('handlers.get_youtube_link', return_value='https://www.youtube.com/results?search_query=x'):
    v = _verify_track_exists('A', 'B')
check("verify: iTunes hit alone verifies", v and v['meta'] is not None, str(v))

with patch('handlers._itunes_track_lookup', return_value=None), \
     patch('handlers.get_youtube_link', return_value='https://www.youtube.com/watch?v=abc123'):
    v2 = _verify_track_exists('A', 'B')
check("verify: YouTube watch link verifies", v2 and v2['yt_url'] is not None, str(v2))

with patch('handlers._itunes_track_lookup', return_value=None), \
     patch('handlers.get_youtube_link', return_value='https://www.youtube.com/results?search_query=A+B'):
    v3 = _verify_track_exists('A', 'B')
check("verify: search-URL fallback does NOT verify", v3 is None, str(v3))

with patch('handlers._itunes_track_lookup', return_value=None), \
     patch('handlers.get_youtube_link', return_value=None):
    check("verify: nothing -> None (garbage keeps not-found)",
          _verify_track_exists('asdfgh', 'qwerty') is None)

# ── 6. Query parsing: primary ordering first ──────────────────────────────
parts = parse_song_query('Chloe Flower - Song for Snow')
check("parse: primary ordering first",
      parts and parts[0] == ('Chloe Flower', 'Song for Snow'), str(parts[:2]))

# ── 7. No-lyrics context store ────────────────────────────────────────────
_NO_LYRICS_CTX.clear()
check("ctx: missing -> None", _pop_no_lyrics_ctx(1, 'A - B') is None)
_NO_LYRICS_CTX[(1, 'a - b')] = {'artist': 'A', 'ts': time.time()}
got1 = _pop_no_lyrics_ctx(1, 'A - B')
check("ctx: fresh pops item", got1 is not None and got1['artist'] == 'A', str(got1))
check("ctx: one-shot (second pop None)", _pop_no_lyrics_ctx(1, 'A - B') is None)
_NO_LYRICS_CTX[(1, 'a - b')] = {'artist': 'A', 'ts': time.time() - 20 * 60}
check("ctx: expired -> None", _pop_no_lyrics_ctx(1, 'A - B') is None)

# ── 8. Mood inference for lyrics-free similar ─────────────────────────────
from services.recommendation_service import _infer_mood_from_title
m = _infer_mood_from_title('Song for Snow', 'Classical', 'focus')
check("mood infer: returns a mood", isinstance(m, str) and len(m) > 0, str(m))
m2 = _infer_mood_from_title('Midnight Drive', 'Dance', '')
check("mood infer: no crash without context", isinstance(m2, str) and len(m2) > 0, str(m2))

# ── 9. Handler map wiring ─────────────────────────────────────────────────
import re
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'handlers.py')).read()
check("wiring: similar_nl in callback map", "'similar_nl': similar_nolyrics_command" in src)
check("wiring: similar_more_nl in callback map", "'similar_more_nl': similar_more_nolyrics_command" in src)

print(f"\n{passed}/{passed + failed} round-21 tests passed")
sys.exit(1 if failed else 0)
