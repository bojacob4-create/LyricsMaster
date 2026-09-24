"""Focused re-test: fix harness fakes, verify translate/mp3/edge paths with clean proxy env."""
import sys, time
sys.path.insert(0, '/home/hatch/workspace/lyrics-master/repo')
import handlers

results = []

class FakeChat:
    id = 555
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

class FakeUser:
    id = 999002; first_name = 'Tester'; username = 'tester'
class FakeUpdate:
    effective_user = FakeUser()
    effective_chat = FakeChat()
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
        if len(blob.strip()) < 2:
            ok, note = False, 'empty reply'
        results.append((ok, name, dt, note, blob[:100].replace('\n', ' | ')))
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

class FakeQuery:
    def __init__(self, data, msg): self.data = data; self.message = msg
    def answer(self, *a, **kw): pass
class FakeCBUpdate:
    effective_user = FakeUser(); effective_chat = FakeChat()
    def __init__(self, data):
        self.callback_query = FakeQuery(data, FakeMsg())

def cb(action, param='Adele - Hello'):
    def go():
        u = FakeCBUpdate(f'{action}:{param}')
        handlers.callback_query_handler(u, FakeCtx())
        out = FakeUpdate(); out.message.texts = u.callback_query.message.texts
        return out
    return go

# stub heavy mp3 download
handlers.download_audio_for_song = lambda artist, song, **kw: (None, 'stubbed-fail')

run('/start', cmd('start_command'), 'lyrics')
run('/subscribe', cmd('subscribe_daily_command'), None)
run('/duel', cmd('duel_command'), None)
run('CB: song', cb('song'), 'Adele')
run('CB: translate_to', cb('translate_to'), 'language')
run('CB: mp3', cb('mp3'), None)
# real translation (needs clean proxy env)
run('/translate Adele-Hello to Spanish', cmd('translate_lyrics_command', 'Adele', '-', 'Hello', 'to', 'Spanish'), None)
run('NL: mp3 hello by adele', nl('mp3 hello by adele'), None)
run('NL: download hello by adele', nl('download hello by adele'), None)
run('NL: similar to hello', nl('songs similar to hello by adele'), None)

fails = [r for r in results if not r[0]]
print(f'TOTAL: {len(results)}  PASS: {len(results)-len(fails)}  FAIL: {len(fails)}')
for ok, name, dt, note, preview in results:
    print(('PASS' if ok else 'FAIL'), f'{dt:6.1f}s', name, '::', note, '::', preview[:70])
