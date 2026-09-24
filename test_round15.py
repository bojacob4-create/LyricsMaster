"""Round-15 tests: user-visible output cleanup.

The user asked (2026-09-24): "cleaning the interfering process of the outputs
that the user see" — report first, then fix. Findings:

1. /start hid half the bot (no /mp3, /download, /translate, /wiki, ...).
2. /start and /help listed commands in two different styles.
3. Buttons renamed the same action ("Video"/"YouTube", "Similar"/"Similar Songs",
   "Full Lyrics"/"Lyrics") depending on the card.
4. Song card + recommend output duplicated buttons as text-command hints.
5. 'decade' in _KNOWN_COMMANDS suggested a /decade command that can't run
   ("Did you mean /decade?" loop); /mp3 and /download had the same problem
   (no CommandHandler registered).
6. Mood mix numbering rendered "*1.*" (bold "1.").

Fixes: /start rewritten (full coverage, same section+▫️ style as /help);
Audio section added to /help; button labels unified to the majority form
("📺 Video", "🎧 Similar Songs", "🎵 Lyrics"); text-hint duplication removed;
'decade' dropped from _KNOWN_COMMANDS; /mp3 + /download registered as real
slash commands and added to the bot menu; mood mix uses plain "1." numbering.

Emojis are kept everywhere — this is dedup/unification, not sterilization.

Run from repo root: ../venv/bin/python test_round15.py
"""
import os, sys
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
import buttons as b

def _text_update(text="/start"):
    update = MagicMock()
    update.effective_user.id = 7
    update.effective_user.first_name = "Test"
    update.message.text = text
    context = MagicMock()
    context.args = []
    context.user_data = {}
    return update, context

def _sent_text(update):
    calls = update.message.reply_text.call_args_list
    return "\n".join(str(c.args[0]) for c in calls if c.args)

print("== /start full coverage ==")
update, context = _text_update()
h.start_command(update, context)
start_text = _sent_text(update)
for cmd in ['song', 'lyrics', 'stats', 'analyze', 'translate', 'recommend',
            'mood', 'extend', 'about', 'throwback', 'newmusic', 'top',
            'trending', 'artist', 'wiki', 'youtube', 'mp3', 'download',
            'quiz', 'duel', 'daily', 'emoji', 'mystats', 'badges',
            'subscribe', 'unsubscribe', 'random']:
    check(f"/start documents /{cmd}", f"/{cmd}" in start_text)
check("/start uses ▫️ section style (same as /help)", "▫️" in start_text)
check("/start has no old 🎵-per-row command list",
      "🎵 */song*" not in start_text)

print("== /help audio section ==")
update, context = _text_update("/help")
h.help_command(update, context)
help_text = _sent_text(update)
check("/help documents /mp3", "/mp3" in help_text)
check("/help documents /download", "/download" in help_text)
check("/help has Audio section", "Audio" in help_text)

print("== button labels unified ==")
def _all_button_texts():
    texts = []
    for builder, args in [
        (b.song_dashboard_buttons, ("adele - hello",)),
        (b.lyrics_buttons, ("adele - hello",)),
        (b.recommend_buttons, ("adele - hello",)),
        (b.recommend_results_buttons, ("adele - hello", [])),
        (b.analyze_buttons, ("adele - hello",)),
        (b.trending_buttons, ("adele - hello",)),
    ]:
        mk = builder(*args)
        for row in mk.inline_keyboard:
            for btn in row:
                texts.append(btn.text)
    return texts
btn_texts = _all_button_texts()
check("no bare '🎧 Similar' (all '🎧 Similar Songs')",
      not any(t == "🎧 Similar" for t in btn_texts), str(btn_texts))
check("no '🎵 Full Lyrics' (all '🎵 Lyrics')",
      not any(t == "🎵 Full Lyrics" for t in btn_texts), str(btn_texts))
check("no '📺 YouTube' (all '📺 Video')",
      not any(t == "📺 YouTube" for t in btn_texts), str(btn_texts))

print("== song card: no duplicated text hints ==")
def _run_song_card(query):
    update = MagicMock()
    update.effective_user.id = 7
    update.effective_chat.id = 7
    processing = MagicMock()
    update.message.reply_text.return_value = processing
    context = MagicMock()
    context.args = query.split()
    context.user_data = {}
    with patch.object(h, 'search_lyrics_with_fallback',
                      return_value=("Adele", "Hello",
                                    "hello it's me\nline two\nline three",
                                    "ok")), \
         patch.object(h, '_is_artist_only_query', return_value=False), \
         patch.object(h, 'get_youtube_link_info', return_value=None), \
         patch.object(h, 'get_similar_songs', return_value=[]), \
         patch.object(h, 'detect_song_mood', return_value='sad'), \
         patch.object(h, 'get_song_statistics',
                      return_value={'total_words': 10, 'total_lines': 3,
                                    'vocabulary_richness': 80}), \
         patch.object(h, 'detect_themes', return_value=['heartbreak']), \
         patch.object(h, 'log_interaction', return_value=None):
        h.song_command(update, context)
    return "\n".join(str(c.args[0]) for c in processing.edit_text.call_args_list if c.args)

card = _run_song_card("Adele - Hello")
check("card has no '🎤 /lyrics' text hint", "🎤 /lyrics" not in card)
check("card has no '🔍 /analyze' text hint", "🔍 /analyze" not in card)
check("card still has Quick Stats", "Quick Stats" in card)
check("card still closes with ━━━", "━━━━━━━━━━━━━━━━━━━━━" in card)

print("== recommend output: no duplicated text hints ==")
from services.recommendation_service import format_recommendations
rec_text = format_recommendations(
    [{'artist': 'Adele', 'name': 'Hello'}], based_on="X - Y")
check("recommend has no '/lyrics' text hint", "/lyrics" not in rec_text)
check("recommend has no '/analyze' text hint", "/analyze" not in rec_text)
check("recommend still closes with ━━━", "━━━━━━━━━━━━━━━━━━━━━" in rec_text)
check("recommend still lists the song", "Adele — Hello" in rec_text)

print("== command registry sanity ==")
check("'decade' not suggested as a slash command",
      'decade' not in h._KNOWN_COMMANDS)
check("'/mp3' is a known command", 'mp3' in h._KNOWN_COMMANDS)
check("'/download' is a known command", 'download' in h._KNOWN_COMMANDS)
upd_dec, ctx_dec = _text_update("/decade")
h.unknown_command_handler(upd_dec, ctx_dec)
dec_sent = _sent_text(upd_dec)
check("/decade no longer suggests itself",
      "Did you mean /decade" not in dec_sent, dec_sent[:80])

print("== /mp3 works as a real command ==")
upd_mp3, ctx_mp3 = _text_update("/mp3")
h.mp3_command(upd_mp3, ctx_mp3)
mp3_sent = _sent_text(upd_mp3)
check("/mp3 with no args gives the button hint (no crash)",
      "MP3 button" in mp3_sent, mp3_sent[:80])

print("== mood mix numbering ==")
fake_songs = [
    {'artist': 'Pharrell Williams', 'name': 'Happy', 'source': 'fresh'},
    {'artist': 'ABBA', 'name': 'Dancing Queen', 'source': 'tag'},
]
fake_msg = MagicMock()
fake_update = MagicMock()
fake_update.message = fake_msg
fake_msg.chat.send_action.return_value = None
with patch.object(h, 'get_mood_mix', return_value=fake_songs), \
     patch.object(h, 'log_interaction', return_value=None):
    h._send_mood_mix(fake_update, 7, 'happy')
mix_text = "\n".join(str(c.args[0]) for c in fake_msg.reply_text.call_args_list if c.args)
check("mix uses plain '1.' numbering", "\n1. " in mix_text or mix_text.startswith("1. ") or "1. 🆕" in mix_text, mix_text[:200])
check("mix has no '*1.*' bold-number artifact", "*1.*" not in mix_text)

print(f"\nround-15: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
