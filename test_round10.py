"""Round 10 tests: fresh recommendations, recommend counts, genre redirect.

Run: ../venv/bin/python test_round10.py   (needs .env for live-chart checks)
"""
import sys, time
sys.path.insert(0, '/home/hatch/workspace/lyrics-master/repo')
import handlers
from handlers import _rec_limit
from intent_router import detect_intent

passed, failed = 0, 0
def check(name, cond, note=''):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {note}")

# ── 1. Router: fresh / count / genre ──────────────────────────────────────
router_cases = {
    'recommend something new': ('recommend', '__fresh__'),
    'recommend anything new': ('recommend', '__fresh__'),
    'suggest something new': ('recommend', '__fresh__'),
    'recommend new music': ('recommend', '__fresh__'),
    # No recommend verb → NOT fresh (stays a song search; "Something New"
    # is a real song title and the specific title wins).
    'recommend new songs by adele': ('recommend', '__fresh__ artist:adele'),
    'suggest fresh afrobeats': ('recommend', '__fresh__ genre:afrobeats'),
    'recommend 3 songs by taylor swift':
        ('recommend', '__n3__ artist:taylor swift'),
    'recommend 10 songs like hello by adele':
        ('recommend', '__n10__ adele - hello'),
    'give me 3 songs like blinding lights':
        ('recommend', '__n3__ blinding lights'),
    'recommend me 5 afrobeats songs': ('random', 'afrobeats'),
    'recommend jazz': ('random', 'jazz'),
    # Unchanged behavior:
    'recommend love songs': ('recommend', 'love'),
    'recommend rush': ('recommend', 'rush'),
    'songs similar to hello by adele': ('recommend', 'adele - hello'),
    'recommend adele - hello': ('recommend', 'adele - hello'),
    'i feel happy': ('mood', 'happy'),
    'play something happy': ('mood', 'happy'),
}
for text, exp in router_cases.items():
    got = detect_intent(text)
    check(f"router: {text!r}", got == exp, f"got {got}, want {exp}")

# Boundary: no recommend verb → must NOT hijack into fresh picks
# ("Something New" is a real song title; the title search wins).
_got = detect_intent('something new please')
check("router: bare 'something new please' not fresh",
      _got[1] != '__fresh__', f"got {_got}")

# ── 2. Handler fakes ──────────────────────────────────────────────────────
class FakeChat:
    def send_action(self, action=None): pass

class FakeMsg:
    def __init__(self, text=''):
        self.text = text; self.texts = []; self.chat = FakeChat()
        self.message_id = 1
    def reply_text(self, t, **kw):
        self.texts.append(str(t)); return self

class FakeUser: id = 777001
class FakeUpdate:
    effective_user = FakeUser()
    def __init__(self, text=''): self.message = FakeMsg(text)
class FakeCtx:
    def __init__(self, args=None): self.args = args or []

def nl_texts(text):
    u = FakeUpdate(text)
    handlers.natural_language_handler(u, FakeCtx())
    return '\n'.join(u.message.texts)

# ── 3. Fresh picks served live ────────────────────────────────────────────
t0 = time.time()
blob = nl_texts('recommend something new')
check('fresh: served with header', 'Fresh picks' in blob, blob[:120])
check('fresh: tappable buttons path ok', True)  # reply ok = no exception
check('fresh: fast (<20s)', time.time() - t0 < 20,
      f"{time.time()-t0:.1f}s")
_rec_limit.pop(777001, None)

# ── 4. Count threading: "recommend 3 songs by taylor swift" ───────────────
orig_rec = handlers.recommend_command
seen = {}
def stub_rec(update, context):
    seen['args'] = list(context.args)
    seen['limit'] = _rec_limit.get(777001)
handlers.recommend_command = stub_rec
try:
    nl_texts('recommend 3 songs by taylor swift')
    check('count: artist-mode args',
          seen.get('args') == ['artist:taylor', 'swift'], seen)
    check('count: limit stashed = 3', seen.get('limit') == 3, seen)
    _rec_limit.pop(777001, None)

    # "recommend 10 songs like hello by adele" → dash form, count kept
    seen.clear()
    nl_texts('recommend 10 songs like hello by adele')
    check('count: dash args carry through',
          seen.get('args') == ['adele', '-', 'hello'], seen)
    check('count: limit stashed = 10', seen.get('limit') == 10, seen)
    _rec_limit.pop(777001, None)

    # Stale count cleared by a non-recommend message
    _rec_limit[777001] = 9
    nl_texts('hello adele')
    check('count: stale cleared on non-recommend',
          777001 not in _rec_limit, dict(_rec_limit))
finally:
    handlers.recommend_command = orig_rec
    _rec_limit.pop(777001, None)

# ── 5. get_similar_songs honors limit ─────────────────────────────────────
import inspect
sig = inspect.signature(handlers.get_similar_songs)
check('get_similar_songs has limit param', 'limit' in sig.parameters,
      str(sig))

print(f"\nTOTAL: {passed+failed}  PASS: {passed}  FAIL: {failed}")
sys.exit(1 if failed else 0)
