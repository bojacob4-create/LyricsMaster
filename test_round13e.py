"""Round-13e tests: mood context chains through card sub-views.

Follow-up to 13d (user wild-test 2026-09-24): the song card showed the mix
mood (Happy), but tapping Analyze flipped it back to Romantic.

Fix: song_command / lyrics_command / analyze_command re-stash the consumed
context mood for their own buttons; the 'lyrics' and 'analyze' callbacks pop
it like 'song' does.  Analyze keeps honest lyric intensity bars but labels
the primary mood from context + a "Spotted in your Happy Mix" note.

Run from repo root: ../venv/bin/python test_round13e.py
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

from unittest.mock import patch, MagicMock
import handlers as h

LYRICS = "ooh ooh\nbody with me yeah\noh you're so good\nooh"

def _ctx(user_id=7, mood="happy"):
    ctx = MagicMock()
    ctx.user_data = {'_card_mood': mood} if mood else {}
    return ctx

def _update(query):
    u = MagicMock()
    u.effective_user.id = 7
    u.effective_chat.id = 7
    u.message.reply_text.return_value = MagicMock()
    return u

print("== context chains: card -> analyze ==")
h._mood_card_context.clear()
upd = _update("ADÉLA - Nicole Kidman")
ctx = _ctx(mood="happy")
ctx.args = "ADÉLA - Nicole Kidman".split()
with patch.object(h, 'search_lyrics_with_fallback',
                  return_value=("ADÉLA", "Nicole Kidman", LYRICS, "ok")), \
     patch.object(h, '_is_artist_only_query', return_value=False), \
     patch.object(h, 'get_youtube_link_info', return_value=None), \
     patch.object(h, 'get_similar_songs', return_value=[]), \
     patch.object(h, 'detect_song_mood', return_value='romantic'), \
     patch.object(h, 'get_song_statistics',
                  return_value={'total_words': 10, 'total_lines': 4,
                                'vocabulary_richness': 80}), \
     patch.object(h, 'detect_themes', return_value=['romantic']), \
     patch.object(h, 'log_interaction', return_value=None):
    h.song_command(upd, ctx)
check("card re-stashes mood for its buttons",
      h._mood_card_context.get((7, "adéla - nicole kidman"), (None,))[0] == "happy")
check("analyze tap would inherit it",
      h._pop_card_mood(7, "ADÉLA - Nicole Kidman") == "happy")

print("== analyze view with context ==")
upd = _update("ADÉLA - Nicole Kidman")
ctx = _ctx(mood="happy")
ctx.args = "ADÉLA - Nicole Kidman".split()
with patch.object(h, 'search_lyrics_with_fallback',
                  return_value=("ADÉLA", "Nicole Kidman", LYRICS, "ok")), \
     patch.object(h, '_is_artist_only_query', return_value=False), \
     patch.object(h, 'detect_song_mood', return_value='romantic'):
    h.analyze_command(upd, ctx)
texts = [str(c.args[0]) for c in upd.message.reply_text.call_args_list if c.args]
out = "\n".join(texts)
check("analyze primary mood is Happy", "🎭 Mood: 😊 Happy" in out, out[:200])
check("analyze keeps honest bars (romantic scored)",
      "Romantic" in out and "/10" in out)
check("analyze notes the mix origin", "Spotted in your" in out and "Happy Mix" in out,
      out[:300])
check("analyze re-stashes for its buttons",
      h._mood_card_context.get((7, "adéla - nicole kidman"), (None,))[0] == "happy")

print("== analyze view without context (direct) ==")
h._mood_card_context.clear()
upd = _update("ADÉLA - Nicole Kidman")
ctx = _ctx(mood=None)
ctx.args = "ADÉLA - Nicole Kidman".split()
with patch.object(h, 'search_lyrics_with_fallback',
                  return_value=("ADÉLA", "Nicole Kidman", LYRICS, "ok")), \
     patch.object(h, '_is_artist_only_query', return_value=False), \
     patch.object(h, 'detect_song_mood', return_value='romantic'):
    h.analyze_command(upd, ctx)
texts = [str(c.args[0]) for c in upd.message.reply_text.call_args_list if c.args]
out = "\n".join(texts)
check("direct /analyze keeps lyric mood", "Romantic" in out, out[:200])
check("direct /analyze has no mix note", "Spotted in your" not in out)

print("== lyrics view with context ==")
h._mood_card_context.clear()
upd = _update("ADÉLA - Nicole Kidman")
ctx = _ctx(mood="happy")
ctx.args = "ADÉLA - Nicole Kidman".split()
with patch.object(h, 'search_lyrics_with_fallback',
                  return_value=("ADÉLA", "Nicole Kidman", LYRICS, "ok")), \
     patch.object(h, 'detect_song_mood', return_value='romantic'), \
     patch.object(h, 'get_song_statistics',
                  return_value={'total_words': 10, 'total_lines': 4,
                                'vocabulary_richness': 80}):
    h.lyrics_command(upd, ctx)
texts = [str(c.args[0]) for c in upd.message.reply_text.call_args_list if c.args]
out = "\n".join(texts)
check("lyrics view shows Happy", "Song mood: 😊 Happy" in out, out[:200])
check("lyrics view re-stashes for its buttons",
      h._mood_card_context.get((7, "adéla - nicole kidman"), (None,))[0] == "happy")

print(f"\nround-13e: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
