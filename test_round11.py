"""Round 11 tests: live-first moods, Audius provider, MP3 retry queue.

Run: ../venv/bin/python test_round11.py   (needs .env for live checks)
"""
import sys, time
sys.path.insert(0, '/home/hatch/workspace/lyrics-master/repo')

passed, failed = 0, 0
def check(name, cond, note=''):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {note}")

# ── 1. Live-first moods (3-tier fresh system) ─────────────────────────────
from services import discovery_service as ds

moods = [m for _, m in ds.MOOD_BUTTONS]
t0 = time.time()
for mood in moods:
    mix = ds.get_mood_mix(mood, 5)
    ok = (isinstance(mix, list) and len(mix) == 5
          and all(s.get('artist') and s.get('name')
                  and s.get('source') in ('fresh', 'tag', 'pool')
                  for s in mix))
    fresh = sum(1 for s in mix if s.get('source') == 'fresh')
    check(f"mood '{mood}': 5 songs, valid source", ok,
          f"got {len(mix) if isinstance(mix, list) else mix!r}")
    # Sad needs only >=2 fresh: on hip-hop-heavy chart days the clash gate
    # (round-13b) correctly blocks hype-genre keyword matches, and the
    # human-curated tag chart is the honest fallback. The invariant that
    # matters — live sources healthy, never the dead pool — still holds.
    need_fresh = 2 if mood == 'sad' else 3
    check(f"mood '{mood}': mostly fresh ({fresh}/5)", fresh >= need_fresh,
          f"only {fresh} fresh picks")
print(f"   (7 moods fetched in {time.time()-t0:.1f}s — fresh tiers + tag chart)")

# Quality gate: every fresh pick must carry a real match reason, and
# keyword picks must genuinely contain the mood word in the title.
import re as _re
for mood in moods:
    internal = ds._MOOD_INTERNAL.get(mood, 'happy')
    kws = ds._MOOD_KEYWORDS.get(internal, set())
    for s in ds.get_mood_mix(mood, 5):
        if s.get('source') != 'fresh':
            continue
        why = s.get('why')
        check(f"mood '{mood}': fresh pick has match reason: {s['name'][:30]!r}",
              why in ('keyword', 'genre', 'search'), f"why={why!r}")
        if why in ('keyword', 'search'):
            words = set(_re.sub(r"[^a-z\s]", "", s['name'].lower()).split())
            check(f"mood '{mood}': title carries mood word: {s['name'][:30]!r}",
                  bool(kws & words), f"title words={sorted(words)[:8]}")
        if mood in ('relaxed', 'focus'):
            m = _re.search(r'\(\s*(\d{2,3})\s*bpm', s['name'], _re.I)
            check(f"mood '{mood}': no 150+bpm track: {s['name'][:30]!r}",
                  not (m and int(m.group(1)) >= 150))

# Dedupe: no repeated artist-title pairs in a mix
for mood in moods:
    mix = ds.get_mood_mix(mood, 5)
    keys = [(s['artist'].lower(), s['name'].lower()) for s in mix]
    check(f"mood '{mood}': no duplicates", len(keys) == len(set(keys)))

# Cache: second call must be instant (no network)
t0 = time.time()
ds.get_mood_mix('happy', 5)
check("mood cache: instant repeat", time.time() - t0 < 0.5,
      f"{time.time()-t0:.2f}s")

# Never raises, even for garbage
check("mood garbage input safe", ds.get_mood_mix('zzz-nope', 5) == []
      or isinstance(ds.get_mood_mix('zzz-nope', 5), list))
check("mood None input safe", isinstance(ds.get_mood_mix(None, 5), list))

# Pool fallback path: simulate every live source down.
ds._MOOD_TAG_CACHE.clear()
import time as _t
for tag in ds._MOOD_LASTFM_TAG.values():
    ds._MOOD_TAG_CACHE[tag] = (_t.time(), [])  # API "returned nothing"
_orig_fresh = ds.get_fresh_entries
_orig_t3 = ds._tier3_picks
ds.get_fresh_entries = lambda *a, **k: []
ds._tier3_picks = lambda *a, **k: []
mix = ds.get_mood_mix('happy', 5)
ds.get_fresh_entries = _orig_fresh
ds._tier3_picks = _orig_t3
check("mood pool fallback: 5 songs when live is empty",
      isinstance(mix, list) and len(mix) == 5,
      f"got {len(mix) if isinstance(mix, list) else mix!r}")
check("mood pool fallback: reasons present",
      all(s.get('reason') for s in mix))
ds._MOOD_TAG_CACHE.clear()  # let the real API repopulate

# Header render: compact legend, no linkifiable domain, per-line markers
import handlers as _handlers
class _FakeChat:
    def send_action(self, action=None): pass
class _FakeMsg:
    chat = _FakeChat()
    def reply_text(self, text, **kw): self.text = text
class _FakeUpdate:
    message = _FakeMsg()
_upd = _FakeUpdate()
_handlers._send_mood_mix(_upd, 123, 'happy')
_txt = _upd.message.text
check("mood render: no bare Last.fm domain (link noise)",
      "Last.fm" not in _txt, _txt[:160])
check("mood render: compact header line",
      "Fresh now" in _txt and _txt.count("Fresh now") == 1)
check("mood render: 5 numbered songs",
      # Round 15: numbering is plain "1." (was "*1.*", bold "1." artifact).
      all(f"\n{i}. " in _txt or _txt.startswith(f"{i}. ") for i in range(1, 6))
      and "*1.*" not in _txt)
check("mood render: per-line freshness markers",
      _txt.count("🆕") >= 3)  # header + fresh song lines

# ── 2. Audius provider ────────────────────────────────────────────────────
from services.youtube_downloader_service import (
    _audius_search_entries, _score_candidate)

entries = _audius_search_entries("tyla water", n=8)
check("audius search returns entries", len(entries) > 0,
      f"got {len(entries)}")
if entries:
    e = entries[0]
    check("audius entry shape", all(k in e for k in
          ('title', 'uploader', 'duration', 'webpage_url')),
          f"keys={list(e.keys())}")
    check("audius stream URL", 'audius.co' in e['webpage_url']
          and '/stream' in e['webpage_url'], e['webpage_url'][:60])
    # Entries must flow through the global scorer without raising
    try:
        s = _score_candidate(e['title'], e['uploader'], e['duration'],
                             'tyla', 'water', 200)
        check("audius entries score cleanly", isinstance(s, (int, float)))
    except Exception as ex:
        check("audius entries score cleanly", False, str(ex))

# ── 3. MP3 retry queue ────────────────────────────────────────────────────
from services.youtube_downloader_service import (
    mp3_block_wave_active, mp3_retry_enqueue, mp3_retry_due,
    mp3_retry_note_attempt, mp3_retry_remove, mp3_forget_failure,
    _mp3_cache_key)

# Isolate the queue file: the bot is LIVE and a real user entry may sit in
# the production queue (round-13b finding: the user's wave-queued MP3
# polluted these tests).  Point the module at a temp file for this section.
import tempfile as _tf
import services.youtube_downloader_service as yds
_orig_retry_json = yds._MP3_RETRY_JSON
yds._MP3_RETRY_JSON = _tf.mkstemp(suffix='.json')[1]

# Queue mechanics (no network)
ok = mp3_retry_enqueue(111, 222, "Test Artist", "Test Song")
check("retry enqueue", ok)
due = mp3_retry_due()
mine = [d for d in due if d.get('artist') == "Test Artist"]
check("retry due lists entry", len(mine) == 1, f"due={len(due)}")
if mine:
    key = mine[0]['key']
    check("retry entry has chat/user", mine[0]['chat_id'] == 111
          and mine[0]['user_id'] == 222)
    mp3_retry_note_attempt(key)
    due2 = [d for d in mp3_retry_due() if d.get('key') == key]
    check("retry attempt counted", due2 and due2[0]['attempts'] == 1,
          f"{due2[0]['attempts'] if due2 else 'gone'}")
    mp3_forget_failure("Test Artist", "Test Song")  # must not raise
    mp3_retry_remove(key)
    check("retry remove", not [d for d in mp3_retry_due()
                               if d.get('key') == key])
check("breaker helper callable", isinstance(mp3_block_wave_active(), bool))

# Block-wave enqueue decision: simulate a breaker-open failure in the
# background job path (breaker forced open, then cleared).
yds._yt_trip_breaker("test")
check("breaker open after trip", mp3_block_wave_active())
# retry_due must return [] while the breaker is open
mp3_retry_enqueue(111, 222, "Wave Artist", "Wave Song")
check("retry due empty during block wave", mp3_retry_due() == [],
      f"got {len(mp3_retry_due())}")
yds._YT_BLOCKED_UNTIL = 0.0  # clear the test breaker
check("breaker closed after clear", not mp3_block_wave_active())
check("retry due resumes after wave",
      any(d.get('artist') == "Wave Artist" for d in mp3_retry_due()))
for d in mp3_retry_due():
    if d.get('artist') in ("Wave Artist", "Test Artist"):
        mp3_retry_remove(d['key'])

# mp3_retry_tick: empty queue → no-op, never raises
import handlers
check("mp3_retry_tick exported", callable(getattr(handlers, 'mp3_retry_tick', None)))

class _FakeBot:
    def send_message(self, chat_id=None, text=None): raise AssertionError("no sends expected")
    def send_audio(self, **kw): raise AssertionError("no sends expected")
try:
    handlers.mp3_retry_tick(_FakeBot())
    check("mp3_retry_tick empty queue no-op", True)
except Exception as ex:
    check("mp3_retry_tick empty queue no-op", False, str(ex))

# mp3_retry_tick delivers a queued success end-to-end
sent = []
class _OKBot:
    def send_message(self, chat_id=None, text=None): sent.append(('msg', text))
    def send_audio(self, chat_id=None, audio=None, caption=None, **kw):
        sent.append(('audio', caption))
mp3_retry_enqueue(999, 888, "Tick Artist", "Tick Song")
real_dl = yds.download_audio_for_song
yds.download_audio_for_song = lambda a, s, on_stage=None: (
    True, ('file_id', 'FAKEFID123', f"{a} - {s}", a))
handlers.download_audio_for_song = yds.download_audio_for_song
try:
    handlers.mp3_retry_tick(_OKBot())
    check("retry tick delivers queued success",
          any(k == 'audio' for k, _ in sent), f"sent={sent}")
    check("retry tick removes delivered entry",
          not any(d.get('artist') == "Tick Artist" for d in mp3_retry_due()))
finally:
    yds.download_audio_for_song = real_dl
    handlers.download_audio_for_song = real_dl
    for d in mp3_retry_due():
        if d.get('artist') == "Tick Artist":
            mp3_retry_remove(d['key'])

# mp3_retry_tick: no-source failure → entry dropped, final notice sent once
sent2 = []
class _OKBot2:
    def send_message(self, chat_id=None, text=None): sent2.append(text)
    def send_audio(self, **kw): raise AssertionError("unexpected audio")
mp3_retry_enqueue(999, 888, "Gone Artist", "Gone Song")
yds.download_audio_for_song = lambda a, s, on_stage=None: (False, "❌ MP3 Not Available\nnope")
handlers.download_audio_for_song = yds.download_audio_for_song
try:
    handlers.mp3_retry_tick(_OKBot2())
    check("retry tick sends final notice on no-source",
          len(sent2) == 1 and "Not Available" in sent2[0], f"sent2={sent2}")
    check("retry tick drops no-source entry",
          not any(d.get('artist') == "Gone Artist" for d in mp3_retry_due()))
finally:
    yds.download_audio_for_song = real_dl
    handlers.download_audio_for_song = real_dl
    yds._MP3_RETRY_JSON = _orig_retry_json  # restore production queue

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
