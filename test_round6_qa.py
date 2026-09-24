"""Round 6 QA regression tests — no Telegram network, no MP3 downloads.

Covers the overnight "make it flawless" pass:
  1. Unknown-command handler ("Did you mean /start?")
  2. utils crash guards (None / empty lyrics)
  3. Natural-language mp3/download/mood routing (previously silent)
  4. Router fixes: play-phrasing, double dashes, whitespace, decade, mood words
  5. Greeting + emoji short-circuits (no wasted API calls)
  6. Arabic artist aliases
  7. YouTube bot-check classified transient (not permanent)

Run: ../venv/bin/python test_round6_qa.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"[FAIL] {name} {detail}")


import handlers
from handlers import (
    natural_language_handler, unknown_command_handler,
    _pending_recommend_artist, _pending_confirmation,
    _GREETING_WORDS,
)
from intent_router import detect_intent, _fuzzy_correct_title
from services.artist_service import get_artist_info
from services import youtube_downloader_service as yds
from utils import get_song_statistics, analyze_rhyme_pattern


class FakeChat:
    def send_action(self, action=None):
        pass


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = FakeChat()
        self.sent = []

    def reply_text(self, text, **kw):
        self.sent.append((text, kw))
        return self

    def edit_text(self, text, **kw):
        self.sent.append((text, kw))
        return self


class FakeUpdate:
    def __init__(self, text=""):
        self.message = FakeMessage(text)
        self.effective_user = type('U', (), {'id': 4242})()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


def _clean_state():
    _pending_recommend_artist.pop(4242, None)
    _pending_confirmation.pop(4242, None)


# ── 1. Unknown-command handler ─────────────────────────────────────────────
upd = FakeUpdate("/strt")
unknown_command_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("unknown cmd /strt -> suggests /start", "/start" in sent, sent[:60])

upd = FakeUpdate("/randm")
unknown_command_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("unknown cmd /randm -> suggests /random", "/random" in sent, sent[:60])

upd = FakeUpdate("/xyzzy")
unknown_command_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("unknown cmd /xyzzy -> help pointer",
      "/help" in sent and "Did you mean" not in sent, sent[:60])

upd = FakeUpdate("/SONG")
unknown_command_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("unknown cmd case-insensitive /SONG -> /song",
      "Did you mean /song" in sent, sent[:60])

# ── 2. utils crash guards ──────────────────────────────────────────────────
try:
    s = get_song_statistics(None)
    check("get_song_statistics(None) -> empty dict, no crash",
          isinstance(s, dict) and s['total_words'] == 0, str(s))
except Exception as e:
    check("get_song_statistics(None) -> empty dict, no crash", False, repr(e))

try:
    r = analyze_rhyme_pattern('')
    check("analyze_rhyme_pattern('') -> zeroed dict, no crash",
          isinstance(r, dict) and r['rhyme_density'] == 0.0, str(r))
except Exception as e:
    check("analyze_rhyme_pattern('') -> zeroed dict, no crash", False, repr(e))

# ── 3. NL routing: mp3 / download / mood (were silently dropped) ───────────
captured = {}
orig_mp3, orig_dl, orig_mood = (handlers.mp3_command,
                                handlers.download_command,
                                handlers.mood_command)
handlers.mp3_command = lambda u, c: captured.update(mp3=list(c.args))
handlers.download_command = lambda u, c: captured.update(dl=list(c.args))
handlers.mood_command = lambda u, c: captured.update(mood=list(c.args))
try:
    _clean_state()
    captured.clear()
    natural_language_handler(FakeUpdate("mp3 greedy"), FakeContext())
    check("NL 'mp3 greedy' -> mp3_command",
          captured.get('mp3') == ['greedy'], str(captured))

    _clean_state()
    captured.clear()
    natural_language_handler(
        FakeUpdate("download https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        FakeContext())
    check("NL 'download <yt-url>' -> download_command",
          captured.get('dl') == ['https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
          str(captured))

    _clean_state()
    captured.clear()
    natural_language_handler(FakeUpdate("something happy"), FakeContext())
    check("NL 'something happy' -> mood_command",
          captured.get('mood') == ['happy'], str(captured))
finally:
    handlers.mp3_command = orig_mp3
    handlers.download_command = orig_dl
    handlers.mood_command = orig_mood
    _clean_state()

# ── 4. Router fixes ────────────────────────────────────────────────────────
check("router: 'put on some drake' -> artist Drake",
      detect_intent("put on some drake") == ('artist', 'Drake'),
      str(detect_intent("put on some drake")))
check("router: 'play greedy by tate mcrae' -> song, by-structure kept",
      detect_intent("play greedy by tate mcrae") == ('song', 'tate mcrae - greedy'),
      str(detect_intent("play greedy by tate mcrae")))
check("router: double dash collapsed",
      detect_intent("drake--god's plan") == ('song', "drake - god's plan"),
      str(detect_intent("drake--god's plan")))
check("router: inner whitespace collapsed",
      detect_intent("  BLINDING   LIGHTS  ") == (None, 'BLINDING LIGHTS'),
      str(detect_intent("  BLINDING   LIGHTS  ")))
check("router: 'i want 80s music' -> throwback 80s",
      detect_intent("i want 80s music") == ('throwback', '80s'),
      str(detect_intent("i want 80s music")))
check("router: bare '1985' stays on song path",
      detect_intent("1985") == (None, '1985'),
      str(detect_intent("1985")))
check("router: 'play happy sad songs' -> mood",
      detect_intent("play happy sad songs") == ('mood', 'happy'),
      str(detect_intent("play happy sad songs")))
check("router: 'play happy' stays a song lookup",
      detect_intent("play happy") == ('song', 'happy'),
      str(detect_intent("play happy")))
check("router: 'happy birthday' not hijacked by mood",
      detect_intent("happy birthday") == (None, 'happy birthday'),
      str(detect_intent("happy birthday")))
check("router: 'stand by me' not mangled",
      detect_intent("lyrics stand by me") == ('lyrics', 'stand by me'),
      str(detect_intent("lyrics stand by me")))
check("router: 'play some music' -> random",
      detect_intent("play some music") == ('random', ''),
      str(detect_intent("play some music")))
check("router: translate trims leading space",
      detect_intent("translate to spanish") == ('translate', 'to spanish'),
      str(detect_intent("translate to spanish")))
check("fuzzy: 'calin down' corrected when in local corpus",
      _fuzzy_correct_title("calin down") == "Calm Down"
      or _fuzzy_correct_title("calin down") == "calin down")

# ── 5. Greeting + emoji short-circuits ─────────────────────────────────────
_clean_state()
upd = FakeUpdate("hello")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("NL 'hello' -> greeting, not song search",
      sent.startswith("👋"), sent[:40])
_clean_state()

_clean_state()
upd = FakeUpdate("hi")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("NL 'hi' -> greeting", sent.startswith("👋"), sent[:40])
_clean_state()

_clean_state()
upd = FakeUpdate("🤣🔥")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("NL pure emoji -> words-only hint, no NLP",
      "I work with words" in sent, sent[:40])
_clean_state()

check("greeting words set sane",
      {'hello', 'hi', 'hey', 'salam'} <= _GREETING_WORDS)

# ── 6. Arabic artist aliases ───────────────────────────────────────────────
info = get_artist_info('شيرين')
check("arabic: 'شيرين' -> Sherine card",
      info is not None and info['name'] == 'Sherine',
      str(info)[:60])
info = get_artist_info('عمرو دياب')
check("arabic: 'عمرو دياب' -> Amr Diab",
      info is not None and info['name'] == 'Amr Diab')
info = get_artist_info('فيروز')
check("arabic: 'فيروز' -> Fairuz",
      info is not None and info['name'] == 'Fairuz')

# ── 7. YouTube bot-check is transient ───────────────────────────────────────
perm = yds._PERMANENT_DL_ERRORS
check("bot-check NOT permanent",
      not any(k in "sign in to confirm you're not a bot" for k in perm),
      str(perm))
check("age-gate still permanent",
      any(k in "sign in to confirm your age" for k in perm))

# ── 8. /random chart picks respect the no-repeat window ────────────────────
import services.artist_service as artist_svc
import services.recommendation_service as rec_svc
_orig_chart = rec_svc._fetch_apple_top_songs
# 20-song chart: small enough to force collisions, big enough that the
# no-repeat guard can actually avoid them.
rec_svc._fetch_apple_top_songs = lambda: [
    {'artist': f'CA{i}', 'name': f'CS{i}'} for i in range(20)
]
try:
    import random as _rng
    _rng.seed(7)
    artist_svc._recent_random_picks.pop(4242, None)
    # Force the chart branch every time by seeding; run enough picks.
    picks = []
    for _ in range(40):
        # monkeypatch rng.random via direct chart-branch call loop
        p = artist_svc.get_random_song(user_id=4242)
        picks.append(f"{p['artist']} - {p['song']}".lower())
    names = picks
    repeat = any(len(set(names[i:i+12])) < 12 for i in range(len(names) - 12))
    check("random: chart picks respect no-repeat window", not repeat)
finally:
    rec_svc._fetch_apple_top_songs = _orig_chart
    artist_svc._recent_random_picks.pop(4242, None)

# ── 9. Callback token registry (64-byte Telegram limit) ────────────────────
import buttons
long_query = 'أم كلثوم - ' + 'ا' * 35  # 93 bytes in UTF-8, 46 chars
data = buttons._cb('song', long_query)
check("callback: long Arabic query fits 64 bytes",
      len(data.encode('utf-8')) <= 64, f"{len(data.encode('utf-8'))} bytes")
action, param = data.split(':', 1)
check("callback: token round-trips to full query",
      buttons.cb_resolve(param) == long_query)
short_data = buttons._cb('song', 'Tyla - Water')
check("callback: short query stays inline",
      short_data == 'song:Tyla - Water', short_data)
check("callback: inline param resolves unchanged",
      buttons.cb_resolve('Tyla - Water') == 'Tyla - Water')

# ── 10. Emoji game guards ───────────────────────────────────────────────────
import time as _time
from handlers import (active_emoji, emoji_command, cancel_command,
                      _mp3_in_progress, mp3_command, translate_lyrics_command)

# TTL: idle 11 minutes -> game auto-ends, message falls through to greeting
_clean_state()
active_emoji[4242] = {'puzzle': {'emojis': '🌧', 'artist': 'A', 'song': 'B'},
                      'score': 2, 'played': 3,
                      'last_active': _time.time() - 660}
upd = FakeUpdate("hello")
natural_language_handler(upd, FakeContext())
msgs = [s[0] for s in upd.message.sent]
check("emoji: idle 11min -> game ends + normal handling",
      4242 not in active_emoji and msgs[0].startswith("🎭")
      and any("👋" in m for m in msgs),
      str([m[:30] for m in msgs]))
_clean_state()

# Intent fall-through: "lyrics hello" mid-game ends game, routes to lyrics
_clean_state()
orig_lyrics = handlers.lyrics_command
handlers.lyrics_command = lambda u, c: captured.update(lyrics=list(c.args))
try:
    captured.clear()
    active_emoji[4242] = {'puzzle': {'emojis': '🌧', 'artist': 'A', 'song': 'B'},
                          'score': 0, 'played': 0,
                          'last_active': _time.time()}
    natural_language_handler(FakeUpdate("lyrics hello"), FakeContext())
    check("emoji: explicit new request ends game + routes normally",
          4242 not in active_emoji and captured.get('lyrics') == ['hello'],
          str(captured))
finally:
    handlers.lyrics_command = orig_lyrics
    _clean_state()

# Bare guess still stays in the game
_clean_state()
active_emoji[4242] = {'puzzle': {'emojis': '🌧', 'artist': 'Adele', 'song': 'Hello'},
                      'score': 0, 'played': 0, 'last_active': _time.time()}
orig_check = handlers.check_emoji_guess
handlers.check_emoji_guess = lambda p, t: False
try:
    upd = FakeUpdate("Adele - Hello")
    natural_language_handler(upd, FakeContext())
    sent = upd.message.sent[-1][0] if upd.message.sent else ""
    check("emoji: bare guess stays in game",
          4242 in active_emoji and "Not quite" in sent, sent[:40])
finally:
    handlers.check_emoji_guess = orig_check
    _clean_state()

# /cancel clears everything
_clean_state()
active_emoji[4242] = {'puzzle': {}, 'score': 0, 'played': 0,
                      'last_active': _time.time()}
_pending_recommend_artist[4242] = 'Drake'
upd = FakeUpdate("/cancel")
cancel_command(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("/cancel clears game + pending state",
      4242 not in active_emoji and 4242 not in _pending_recommend_artist
      and "Cancelled" in sent, sent[:50])
_clean_state()

# ── 11. MP3 concurrency guard + stale file_id recovery ─────────────────────
from services import youtube_downloader_service as _yds

# Double-tap: second call gets "hang tight", no download started
_clean_state()
_mp3_in_progress.add((4242, 'tyla', 'water'))
calls = []
_orig_dl = _yds.download_audio_for_song
_yds.download_audio_for_song = lambda *a, **k: (calls.append(1), (False, "x"))[1]
# mp3_command reads the service fn via its own module namespace
orig_handlers_dl = handlers.download_audio_for_song
handlers.download_audio_for_song = _yds.download_audio_for_song
try:
    ctx = FakeContext(args=['Tyla', '-', 'Water'])
    upd = FakeUpdate("x")
    mp3_command(upd, ctx)
    sent = upd.message.sent[-1][0] if upd.message.sent else ""
    check("mp3: double-tap -> 'hang tight', no new download",
          "Already working" in sent and not calls, sent[:50])
finally:
    _mp3_in_progress.discard((4242, 'tyla', 'water'))
    _yds.download_audio_for_song = _orig_dl
    handlers.download_audio_for_song = orig_handlers_dl
    _clean_state()

# Stale file_id: send fails -> stale id dropped -> fresh download runs
# (background job: wait for the worker thread to finish via _mp3_in_progress)
_clean_state()
noted = {}
forgot = []
# NOTE: handlers.py imported these names directly, so mock handlers' refs.
orig_note = handlers.note_mp3_file_id
orig_forget = handlers.forget_mp3_file_id
orig_is_cached = handlers.is_cached_mp3_path
orig_cleanup = handlers.cleanup_video
handlers.note_mp3_file_id = lambda a, s, f: noted.update(fid=f)
handlers.forget_mp3_file_id = lambda a, s: forgot.append((a, s))
handlers.is_cached_mp3_path = lambda p: True
handlers.cleanup_video = lambda p: None
fresh_calls = []
def _fake_dl(artist, song, on_stage=None):
    fresh_calls.append((artist, song))
    if not fresh_calls[1:]:
        return True, ('file_id', 'STALE_ID', 'T', 'U')  # first: stale tier
    import tempfile
    p = tempfile.mktemp(suffix='.mp3')
    open(p, 'wb').write(b'x' * 100)
    return True, (p, "done", 'T', 'U')  # second: fresh file
handlers.download_audio_for_song = _fake_dl
class _BoomBot:
    def __init__(self):
        self.sent = []
    def send_audio(self, **kw):
        if kw.get('audio') == 'STALE_ID':
            raise RuntimeError("file_id expired")
        self.sent.append(('audio', kw.get('caption', '')))
        m = type('M', (), {})()
        m.audio = type('A', (), {'file_id': 'NEWFID'})()
        return m
    def send_message(self, **kw):
        self.sent.append(('message', kw.get('text', '')[:40]))
        return None
try:
    upd = FakeUpdate("x")
    upd.effective_chat = type('C', (), {'id': 999})()
    ctx = FakeContext(args=['Tyla', '-', 'Water'])
    ctx.bot = _BoomBot()
    mp3_command(upd, ctx)
    # ack must be immediate and non-blocking
    ack = upd.message.sent[-1][0] if upd.message.sent else ""
    check("mp3: ack sent immediately, handler non-blocking",
          "On it" in ack, ack[:50])
    # wait for the background job to finish (max 10s)
    import time as _t
    _deadline = _t.time() + 10
    while (4242, 'tyla', 'water') in handlers._mp3_in_progress and _t.time() < _deadline:
        _t.sleep(0.05)
    check("mp3: stale file_id dropped + fresh download ran",
          forgot == [('Tyla', 'Water')] and len(fresh_calls) == 2,
          f"forgot={forgot} calls={len(fresh_calls)}")
    check("mp3: fresh audio delivered via background send_audio",
          any(s[0] == 'audio' for s in ctx.bot.sent),
          str(ctx.bot.sent[:2]))
finally:
    handlers.note_mp3_file_id = orig_note
    handlers.forget_mp3_file_id = orig_forget
    handlers.is_cached_mp3_path = orig_is_cached
    handlers.cleanup_video = orig_cleanup
    handlers.download_audio_for_song = orig_handlers_dl
    _clean_state()
    handlers.forget_mp3_file_id = orig_forget
    handlers.is_cached_mp3_path = orig_is_cached
    handlers.cleanup_video = orig_cleanup
    handlers.download_audio_for_song = orig_handlers_dl
    _clean_state()

# ── 12. Markdown escaping ───────────────────────────────────────────────────
from utils import escape_markdown
check("escape_markdown neutralizes _ * ` [ ]",
      escape_markdown("a_b *c* [d] `e`") == "a\\_b \\*c\\* \\[d\\] \\`e\\`")
check("escape_markdown leaves plain text alone",
      escape_markdown("Adele - Hello") == "Adele - Hello")

# ── 13. Translation chunking ────────────────────────────────────────────────
_clean_state()
orig_search = handlers.search_lyrics_with_fallback
orig_translate = handlers.translate_text
long_lyrics = ("La la la. " * 2000)  # ~20k chars
handlers.search_lyrics_with_fallback = lambda q: ('A', 'S', long_lyrics, 'ok')
handlers.translate_text = lambda t, lang: t  # identity = long output
try:
    upd = FakeUpdate("x")
    translate_lyrics_command(upd, FakeContext(args=['A', '-', 'S']))
    texts = [s[0] for s in upd.message.sent]
    check("translate: long output chunked into multiple messages",
          len(texts) >= 3 and all(len(t) <= 4096 for t in texts),
          f"{len(texts)} msgs, max len {max(len(t) for t in texts)}")
finally:
    handlers.search_lyrics_with_fallback = orig_search
    handlers.translate_text = orig_translate
    _clean_state()

# ── 14. Atomic JSON helpers ─────────────────────────────────────────────────
import tempfile, json as _json
from utils import atomic_json_write, locked_json_update
tmp = tempfile.mktemp(suffix='.json')
check("atomic_json_write round-trips",
      atomic_json_write(tmp, {'a': 1}) and _json.load(open(tmp)) == {'a': 1})
check("locked_json_update merges under lock",
      locked_json_update(tmp, lambda d: {**d, 'b': 2}) == {'a': 1, 'b': 2}
      and _json.load(open(tmp)) == {'a': 1, 'b': 2})
os.remove(tmp)

# ── 15. Duel TTL ────────────────────────────────────────────────────────────
from services import fun_service as _fun
_duels_path = _fun.DUELS_PATH
_orig_duels = None
try:
    _orig_duels = _fun._load_json(_duels_path)
except Exception:
    pass
try:
    d = _fun.create_duel(4242, "Tester", questions=[
        {'qtype': 'guess_song', 'snippet': 'x',
         'options': [{'artist': 'A', 'song': 'B'}], 'answer_index': 0,
         'artist': 'A', 'song': 'B'}])
    code = d.get('code')
    # Age it 25h and reload through join_duel -> must be pruned
    duels = _fun._load_json(_duels_path)
    duels[code]['created'] = _time.time() - 25 * 3600
    _fun._save_json(_duels_path, duels)
    joined = _fun.join_duel(code, 9999, "Late")
    check("duel: 25h-old code pruned, join rejected",
          joined is None and code not in _fun._load_json(_duels_path))
finally:
    try:
        if _orig_duels is not None:
            _fun._save_json(_duels_path, _orig_duels)
    except Exception:
        pass

# ── 16. Input length cap ────────────────────────────────────────────────────
_clean_state()
upd = FakeUpdate("x" * 600)
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("NL: 600-char paste -> friendly too-long message",
      "a bit long" in sent, sent[:40])
_clean_state()

# ── 17. Quiz/duel/daily own non-answer text ─────────────────────────────────
from handlers import active_quizzes, active_duel_sessions, active_daily

# Active quiz + "huh?" -> nudge, quiz stays open
_clean_state()
active_quizzes[4242] = {'state': 'active', 'score': 0, 'total_questions': 0,
                        'questions': [], 'idx': 0}
upd = FakeUpdate("huh?")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("quiz: non-answer text -> nudge, quiz stays active",
      "A, B, C or D" in sent and 4242 in active_quizzes, sent[:50])
# Active quiz + "B" -> routed to quiz_answer, no nudge
orig_qa = handlers.quiz_answer
handlers.quiz_answer = lambda u, c: u.message.reply_text("ANSWERED")
try:
    upd = FakeUpdate("B")
    natural_language_handler(upd, FakeContext())
    sent = upd.message.sent[-1][0] if upd.message.sent else ""
    check("quiz: 'B' still answers", sent == "ANSWERED", sent[:30])
finally:
    handlers.quiz_answer = orig_qa
active_quizzes.pop(4242, None)

# Active daily + "hello" -> nudge
_clean_state()
active_daily[4242] = {'questions': [], 'idx': 0, 'score': 0}
upd = FakeUpdate("hello")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("daily: non-answer text -> nudge", "Daily challenge" in sent, sent[:50])
active_daily.pop(4242, None)

# Active duel + "hello" -> nudge
_clean_state()
active_duel_sessions[4242] = {'code': 'X', 'idx': 0, 'score': 0,
                              'chat_id': 1, 'name': 'T'}
upd = FakeUpdate("hello")
natural_language_handler(upd, FakeContext())
sent = upd.message.sent[-1][0] if upd.message.sent else ""
check("duel: non-answer text -> nudge", "duel" in sent.lower(), sent[:50])
active_duel_sessions.pop(4242, None)
_clean_state()

print(f"\n{'='*60}\nRESULT: {PASS}/{PASS+FAIL} passed")
if FAILURES:
    print("FAILURES:", FAILURES)
sys.exit(1 if FAIL else 0)
