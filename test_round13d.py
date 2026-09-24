"""Round-13d tests: mood-mix -> song-card mood consistency.

The bug (user wild-test 2026-09-24): "ADELA - Nicole Kidman" appeared in the
Happy Mix, but its song card Quick Stats said "Mood: Romantic" — the mix
builder (chart/genre signals) and detect_song_mood (lyric signals) disagreed
and the bot contradicted itself.

Fix: _send_mood_mix stashes the mix mood per song; the 'song' callback pops
it (one-shot, 15-min TTL) into context.user_data['_card_mood']; song_command
prefers it over detect_song_mood.  Direct searches keep lyric analysis.

Run from repo root: ../venv/bin/python test_round13d.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed, failed = 0, 0
def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {extra}")

print("== mood card context (unit) ==")
import handlers as h

# fresh pop returns the stashed mood and consumes the entry (one-shot)
h._mood_card_context.clear()
h._mood_card_context[(7, "adéla - nicole kidman")] = ("happy", time.time())
check("pop returns stashed mood",
      h._pop_card_mood(7, "ADÉLA - Nicole Kidman") == "happy")
check("entry consumed after pop",
      h._pop_card_mood(7, "ADÉLA - Nicole Kidman") is None)

# unknown user / song -> None
h._mood_card_context.clear()
h._mood_card_context[(7, "adele - hello")] = ("sad", time.time())
check("other user gets None", h._pop_card_mood(8, "adele - hello") is None)
check("entry still there for right user",
      h._pop_card_mood(7, "adele - hello") == "sad")

# expired entry -> None (and consumed)
h._mood_card_context.clear()
h._mood_card_context[(7, "x - y")] = ("happy", time.time() - 901)
check("expired entry returns None", h._pop_card_mood(7, "x - y") is None)
check("expired entry consumed", (7, "x - y") not in h._mood_card_context)

# empty/None query safe
check("empty query safe", h._pop_card_mood(7, "") is None)

print("== _send_mood_mix stashes context (mocked) ==")
from unittest.mock import patch, MagicMock

h._mood_card_context.clear()
fake_songs = [
    {'artist': 'ADÉLA', 'name': 'Nicole Kidman', 'source': 'fresh'},
    {'artist': 'Stella Lefty', 'name': 'Boston', 'source': 'fresh'},
]
fake_msg = MagicMock()
fake_update = MagicMock()
fake_update.message = fake_msg
fake_msg.chat.send_action.return_value = None

with patch.object(h, 'get_mood_mix', return_value=fake_songs):
    h._send_mood_mix(fake_update, 7, 'happy')

check("mix stashed mood for song 1",
      h._mood_card_context.get((7, "adéla - nicole kidman"), (None,))[0] == "happy")
check("mix stashed mood for song 2",
      h._mood_card_context.get((7, "stella lefty - boston"), (None,))[0] == "happy")
check("tap from mix resolves to mix mood",
      h._pop_card_mood(7, "ADÉLA - Nicole Kidman") == "happy")

print("== song card prefers context mood (mocked) ==")

def _run_song_card(query, card_mood=None):
    """Run song_command with everything stubbed; return the final card text."""
    import types
    update = MagicMock()
    update.effective_user.id = 7
    update.effective_chat.id = 7
    processing = MagicMock()
    update.message.reply_text.return_value = processing
    context = MagicMock()
    context.args = query.split()
    context.user_data = {}
    if card_mood:
        context.user_data['_card_mood'] = card_mood
    with patch.object(h, 'search_lyrics_with_fallback',
                      return_value=("ADÉLA", "Nicole Kidman",
                                    "ooh ooh\nbody with me yeah\noh you're so good\nooh",
                                    "ok")), \
         patch.object(h, '_is_artist_only_query', return_value=False), \
         patch.object(h, 'get_youtube_link_info', return_value=None), \
         patch.object(h, 'get_similar_songs', return_value=[]), \
         patch.object(h, 'detect_song_mood', return_value='romantic'), \
         patch.object(h, 'get_song_statistics',
                      return_value={'total_words': 10, 'total_lines': 4,
                                    'vocabulary_richness': 80}), \
         patch.object(h, 'detect_themes', return_value=['romantic']), \
         patch.object(h, 'log_interaction', return_value=None):
        h.song_command(update, context)
    # final card goes through processing_msg.edit_text
    texts = [str(c.args[0]) for c in processing.edit_text.call_args_list if c.args]
    return "\n".join(texts)

card_ctx = _run_song_card("ADÉLA - Nicole Kidman", card_mood="happy")
check("card from happy mix shows Mood: Happy",
      "Mood: Happy" in card_ctx, card_ctx[:120])
check("card from happy mix does NOT say Romantic",
      "Mood: Romantic" not in card_ctx)

card_direct = _run_song_card("ADÉLA - Nicole Kidman")
check("direct search keeps lyric analysis (Romantic)",
      "Mood: Romantic" in card_direct, card_direct[:120])

print(f"\nround-13d: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
