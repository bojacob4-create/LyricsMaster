"""Adversarial deep test: every slash command + NL trick + callback button.
Run: ../venv/bin/python test_adversarial.py   (network-heavy, ~10 min)
"""
import sys, time
sys.path.insert(0, '/home/hatch/workspace/lyrics-master/repo')
import handlers

results = []

class FakeChat:
    def send_action(self, action=None): pass

class FakeMsg:
    def __init__(self, text=''):
        self.text = text; self.texts = []; self.chat = FakeChat(); self.message_id = 1
    def reply_text(self, t, **kw):
        self.texts.append(str(t)); return self
    def edit_text(self, t, **kw):
        self.texts.append('EDIT:' + str(t)); return self
    def reply_audio(self, *a, **kw):
        self.texts.append('AUDIO_SENT'); return self
    def reply_video(self, *a, **kw):
        self.texts.append('VIDEO_SENT'); return self

class FakeUser: id = 999001
class FakeUpdate:
    effective_user = FakeUser()
    def __init__(self, text=''): self.message = FakeMsg(text)
class FakeCtx:
    def __init__(self, args=None): self.args = args or []

def run(name, fn, expect=None):
    t0 = time.time()
    try:
        u = fn()
        dt = time.time() - t0
        texts = getattr(getattr(u, 'message', None), 'texts', []) or []
        blob = '\n'.join(texts)
        ok, note = True, ''
        if expect and expect.lower() not in blob.lower():
            ok, note = False, f'missing {expect!r}'
        if len(blob.strip()) < 2 and 'AUDIO_SENT' not in blob:
            ok, note = False, 'empty reply'
        results.append((ok, name, dt, note, blob[:110].replace('\n', ' | ')))
    except Exception as e:
        dt = time.time() - t0
        results.append((False, name, dt, f'{type(e).__name__}: {e}', ''))

def cmd(fn_name, *args):
    def go():
        u = FakeUpdate()
        getattr(handlers, fn_name)(u, FakeCtx(list(args)))
        return u
    return go

def nl(text):
    def go():
        u = FakeUpdate(text)
        handlers.natural_language_handler(u, FakeCtx())
        return u
    return go

# ── stub the heavy MP3 download so the harness doesn't burn 5 min per case ──
handlers.download_audio_for_song = lambda artist, song, **kw: (None, 'stubbed-fail')

# ═══════════════════════ 1. SLASH COMMANDS ═══════════════════════
run('/start', cmd('start_command'), 'lyrics')
run('/help', cmd('help_command'), '/song')
run('/about', cmd('about_command'))
run('/song no-args', cmd('song_command'), None)
run('/song valid', cmd('song_command', 'Adele', '-', 'Hello'), 'Adele')
run('/song garbage', cmd('song_command', 'xyzqwe123abc'), None)
run('/song bare-title', cmd('song_command', 'Hello'), None)
run('/lyrics valid', cmd('lyrics_command', 'Adele', '-', 'Hello'), 'Hello')
run('/lyrics garbage', cmd('lyrics_command', 'xyzqwe123abc'), None)
run('/translate no-args', cmd('translate_lyrics_command'), None)
run('/translate valid', cmd('translate_lyrics_command', 'Adele', '-', 'Hello'), None)
run('/translate +lang', cmd('translate_lyrics_command', 'Adele', '-', 'Hello', 'to', 'Spanish'), None)
run('/translate lang-only', cmd('translate_lyrics_command', 'to', 'Spanish'), None)
run('/recommend no-args', cmd('recommend_command'), None)
run('/recommend valid', cmd('recommend_command', 'Adele', '-', 'Hello'), None)
run('/recommend ambiguous', cmd('recommend_command', 'rush'), None)
run('/artist no-args', cmd('artist_command'), None)
run('/artist valid', cmd('artist_command', 'Adele'), 'Adele')
run('/artist garbage', cmd('artist_command', 'xyzqwe123abc'), None)
run('/top no-args', cmd('top_command'), None)
run('/top pop', cmd('top_command', 'pop'), None)
run('/top garbage-genre', cmd('top_command', 'xyzgenre'), None)
run('/trending', cmd('trending_command'), None)
run('/random no-args', cmd('random_command'), None)
run('/random soul', cmd('random_command', 'soul'), None)
run('/random afrobeats', cmd('random_command', 'afrobeats'), None)
run('/random garbage-genre', cmd('random_command', 'xyzgenre'), None)
run('/analyze valid', cmd('analyze_command', 'Adele', '-', 'Hello'), None)
run('/analyze no-args', cmd('analyze_command'), None)
run('/stats valid', cmd('stats_command', 'Adele', '-', 'Hello'), None)
run('/stats no-args', cmd('stats_command'), None)
run('/mystats', cmd('mystats_command'), None)
run('/mood happy', cmd('mood_command', 'happy'), None)
run('/mood garbage', cmd('mood_command', 'xyzmood'), None)
run('/mood no-args', cmd('mood_command'), None)
run('/youtube valid', cmd('youtube_command', 'Adele', '-', 'Hello'), 'youtube')
run('/youtube no-args', cmd('youtube_command'), None)
run('/subscribe', cmd('subscribe_daily_command'), None)
run('/unsubscribe', cmd('unsubscribe_daily_command'), None)
run('/daily', cmd('daily_command'), None)
run('/badges', cmd('badges_command'), None)
run('/cancel', cmd('cancel_command'), None)
run('/newmusic', cmd('newmusic_command'), None)
run('/newmusic pop', cmd('newmusic_command', 'pop'), None)
run('/throwback 90s', cmd('throwback_command', '90s'), None)
run('/throwback garbage', cmd('throwback_command', 'xyz'), None)
run('/throwback no-args', cmd('throwback_command'), None)
run('/wiki adele', cmd('wiki_command', 'Adele'), 'Adele')
run('/wiki no-args', cmd('wiki_command'), None)
run('/emoji start', cmd('emoji_command'), None)
run('/extend no-args', cmd('extend_command'), None)
run('/duel no-args', cmd('duel_command'), None)

print('part 1 done', flush=True)

# ═══════════════════════ 2. NL TRICKS ═══════════════════════
run('NL: Translate to Spanish (no song)', nl('Translate to Spanish'), None)
run('NL: translate to spanish lower', nl('translate to spanish'), None)
run('NL: TRANSLATE TO FRENCH', nl('TRANSLATE TO FRENCH'), None)
run('NL: bare "spanish" no pending', nl('spanish'), None)
run('NL: full form', nl('Translate Adele - Hello to Spanish'), 'Hello')
run('NL: Adele - Hello in Spanish', nl('Adele - Hello in Spanish'), None)
run('NL: Translate to Klingon', nl('Translate to Klingon'), None)
run('NL: translate (bare)', nl('translate'), None)
run('NL: Hello by Adele', nl('Hello by Adele'), 'Adele')
run('NL: adele hello', nl('adele hello'), None)
run('NL: song by adele', nl('song by adele'), None)
run('NL: play hello by adele', nl('play hello by adele'), None)
run('NL: typo adelle hello', nl('adelle hello'), None)
run('NL: rush ambiguous', nl('rush'), None)
run('NL: ghost bare', nl('ghost'), None)
run('NL: hello bare', nl('hello'), None)
run('NL: "2" no pending', nl('2'), None)
run('NL: hi', nl('hi'), None)
run('NL: thanks', nl('thanks'), None)
run('NL: emoji only', nl('🎵'), None)
run('NL: empty', nl(''), None)
run('NL: very long', nl('a ' * 300), None)
run('NL: random (bare)', nl('random'), None)
run('NL: quiz (bare)', nl('quiz'), None)
run('NL: who is adele', nl('who is adele'), 'Adele')
run('NL: adele wiki', nl('adele wiki'), None)
run('NL: recommend songs like hello', nl('recommend songs like hello'), None)
run('NL: mp3 hello by adele', nl('mp3 hello by adele'), None)
run('NL: lyrics of hello by adele', nl('lyrics of hello by adele'), 'Hello')
run('NL: top pop', nl('top pop'), None)
run('NL: trending songs', nl('trending songs'), None)
run('NL: new music', nl('new music'), None)
run('NL: throwback 90s', nl('throwback 90s'), None)
run('NL: songs like blinding lights', nl('songs like blinding lights'), None)
run('NL: what is the mood of hello', nl('what is the mood of hello'), None)
run('NL: arabic-only', nl('ترجم أغنية'), None)

# pending-translate flows
def pending_a():
    handlers._pending_translate_lang[999001] = {'query': 'Adele - Hello', 'lang_code': None, 'ts': time.time()}
    return nl('French')()
run('NL: pending lang <- French', pending_a, None)
def pending_a_bad():
    handlers._pending_translate_lang[999001] = {'query': 'Adele - Hello', 'lang_code': None, 'ts': time.time()}
    return nl('Klingon')()
run('NL: pending lang <- Klingon', pending_a_bad, 'support')
def pending_a_newreq():
    handlers._pending_translate_lang[999001] = {'query': 'Adele - Hello', 'lang_code': None, 'ts': time.time()}
    return nl('random soul')()
run('NL: pending lang <- new request', pending_a_newreq, None)
def pending_b():
    handlers._pending_translate_lang[999001] = {'query': None, 'lang_code': 'es', 'lang_name': 'Spanish', 'ts': time.time()}
    handlers._last_song.pop(999001, None)
    return nl('Adele - Hello')()
run('NL: pending song <- Adele - Hello', pending_b, None)

print('part 2 done', flush=True)

# ═══════════════════════ 3. CALLBACK BUTTONS ═══════════════════════
class FakeQuery:
    def __init__(self, data, msg):
        self.data = data; self.message = msg
    def answer(self, *a, **kw): pass

class FakeCBUpdate:
    effective_user = FakeUser()
    def __init__(self, data):
        self.callback_query = FakeQuery(data, FakeMsg())
        self.effective_message = self.callback_query.message

def cb(action, param='Adele - Hello'):
    def go():
        u = FakeCBUpdate(f'{action}:{param}')
        handlers.callback_query_handler(u, FakeCtx())
        # surface the inner message texts
        out = FakeUpdate(); out.message.texts = u.callback_query.message.texts
        return out
    return go

for action in ['song', 'lyrics', 'recommend', 'artist', 'youtube', 'trending',
               'translate', 'translate_to', 'analyze', 'stats', 'top', 'random',
               'wiki', 'mood', 'decade', 'artistsongs', 'emoji_exit', 'noop']:
    run(f'CB: {action}', cb(action), None)
run('CB: more_recs', cb('more_recs'), None)
run('CB: mp3 (stubbed dl)', cb('mp3'), None)
run('CB: unknown action', cb('boguous_action_xyz'), None)

def _cb_malformed():
    u = FakeCBUpdate('nodividerhere')
    handlers.callback_query_handler(u, FakeCtx())
    out = FakeUpdate(); out.message.texts = u.callback_query.message.texts
    return out
run('CB: malformed data', _cb_malformed, None)

# ═══════════════════════ 4. QUIZ FLOW ═══════════════════════
run('quiz start', cmd('quiz_command'), None)
run('quiz answer 1', nl('1'), None)
run('quiz answer garbage', nl('xyzanswer'), None)
run('/endquiz', cmd('end_quiz_command'), None)
run('/quiz again + /cancel', cmd('quiz_command'), None)
run('/cancel mid-quiz', cmd('cancel_command'), None)
run('/endquiz no-game', cmd('end_quiz_command'), None)

# ═══════════════════════ REPORT ═══════════════════════
fails = [r for r in results if not r[0]]
slow = sorted([r for r in results if r[2] > 20], key=lambda r: -r[2])
print(f'\n{"="*60}\nTOTAL: {len(results)}  PASS: {len(results)-len(fails)}  FAIL: {len(fails)}')
for ok, name, dt, note, preview in fails:
    print(f'FAIL  {dt:6.1f}s  {name} :: {note} :: {preview[:80]}')
print('\nSLOWEST (>20s):')
for ok, name, dt, note, preview in slow[:12]:
    print(f'      {dt:6.1f}s  {name}')
print('\nSLOWEST overall top 8:')
for ok, name, dt, note, preview in sorted(results, key=lambda r: -r[2])[:8]:
    print(f'      {dt:6.1f}s  {name}')
