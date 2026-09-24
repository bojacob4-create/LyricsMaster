"""Round-35 tests: /mp3 via the home worker (audio jobs).

The streamer now downloads MP3s over the home IP (which YouTube doesn't
block), the same way it does video. Server side:
- post_job(..., kind="audio", artist, song) + get_job_entry()
- HONEST_FAIL_MSGS gains audio_too_long / audio_too_large (track wording)
- mp3_cached_lookup(): Tier 0/1/1.5 extracted, shared by both paths
- resolve_mp3_youtube_url(): best YouTube URL for a song (worker input)
- _mp3_background_job: caches → worker → local path
- worker_channel_post: DONE audio → copyMessage + file_id cache;
  FAIL audio → honest notice (permanent) or threaded local fallback
- worker_timeout_tick: expired audio jobs → mp3 fallback
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from services import home_worker_service as svc
from services import youtube_downloader_service as yds

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def _fresh_store():
    tmp = tempfile.mkdtemp()
    svc._JOB_STORE = os.path.join(tmp, "worker_jobs.json")
    return tmp


def _with_env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    os.environ.update(kw)

    def restore():
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeAudio:
    def __init__(self, file_id):
        self.file_id = file_id


class FakeSentMessage:
    def __init__(self, file_id="FID123"):
        self.audio = FakeAudio(file_id)


class FakeBot:
    def __init__(self, sent_file_id="FID123"):
        self.sent = []
        self.copies = []
        self.sent_file_id = sent_file_id

    def send_message(self, chat_id=None, text=None, **kw):
        self.sent.append((chat_id, text))

    def copy_message(self, chat_id=None, from_chat_id=None,
                     message_id=None, caption=None):
        self.copies.append({"chat_id": chat_id, "from_chat_id": from_chat_id,
                            "message_id": message_id, "caption": caption})
        return FakeSentMessage(self.sent_file_id)


class FakePost:
    def __init__(self, text, chat_id):
        self.text = text
        self.chat = FakeChat(chat_id)


class FakeUpdate:
    def __init__(self):
        self.channel_post = None


class FakeContext:
    def __init__(self, bot=None):
        self.bot = bot or FakeBot()


# --------------------------------- post_job: audio ------------------------
def t_post_job_audio_kind():
    print("-- post_job stores kind/artist/song; get_job_entry reads them --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    try:
        jid = svc.post_job(42, 7, "https://youtu.be/dQw4w9WgXcQ",
                           title="A - S", kind="audio",
                           artist="A", song="S")
        check("audio job posted", bool(jid))
        entry = svc.get_job_entry(jid)
        check("kind stored", entry and entry.get("kind") == "audio")
        check("artist/song stored",
              entry and entry.get("artist") == "A" and entry.get("song") == "S")
        jid2 = svc.post_job(42, 7, "https://youtu.be/dQw4w9WgXcQ",
                            kind="weird")
        check("unknown kind tolerated as video",
              svc.get_job_entry(jid2).get("kind") == "video")
        check("get_job_entry unknown → None", svc.get_job_entry("nope") is None)
    finally:
        svc._api_send_message = orig
        restore()


def t_honest_audio_msgs():
    print("-- HONEST_FAIL_MSGS: audio variants use track wording --")
    m = svc.HONEST_FAIL_MSGS
    check("audio_too_long present", "audio_too_long" in m)
    check("audio_too_large present", "audio_too_large" in m)
    check("audio_too_long says Track (not Video)",
          "Track Too Long" in m["audio_too_long"]
          and "Video" not in m["audio_too_long"])
    check("audio notices keep 😕 (no ❌)",
          all("❌" not in m[k]
              for k in ("audio_too_long", "audio_too_large")))


# --------------------------------- mp3_cached_lookup ---------------------
def t_mp3_cached_lookup():
    print("-- mp3_cached_lookup: tiers + miss + never raises --")
    orig_fid, orig_disk, orig_fail = (yds._fileid_get, yds._disk_cache_get,
                                     yds._failure_get)
    try:
        yds._fileid_get = lambda k: "CACHEDFID"
        yds._disk_cache_get = lambda k: (_ for _ in ()).throw(
            AssertionError("disk must not run after file_id hit"))
        yds._failure_get = lambda k: (_ for _ in ()).throw(
            AssertionError("failure mem must not run after file_id hit"))
        r = yds.mp3_cached_lookup("A", "S")
        check("file_id hit", r and r[0] is True and r[1][0] == "file_id"
              and r[1][1] == "CACHEDFID")

        yds._fileid_get = lambda k: None
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        yds._disk_cache_get = lambda k: path
        r = yds.mp3_cached_lookup("A", "S")
        check("disk hit", r and r[0] is True and r[1][0] == path
              and "⚡ Served from cache" in r[1][1])
        os.remove(path)

        yds._disk_cache_get = lambda k: None
        yds._failure_get = lambda k: ("😕 busy", 12)
        r = yds.mp3_cached_lookup("A", "S")
        check("failure memory hit",
              r and r[0] is False and "retry in a few minutes" in r[1])

        yds._failure_get = lambda k: None
        r = yds.mp3_cached_lookup("A", "S")
        check("cache miss → None", r is None)

        yds._fileid_get = lambda k: (_ for _ in ()).throw(RuntimeError("x"))
        check("never raises", yds.mp3_cached_lookup("A", "S") is None)
    finally:
        yds._fileid_get, yds._disk_cache_get, yds._failure_get = (
            orig_fid, orig_disk, orig_fail)


# --------------------------------- resolve_mp3_youtube_url ---------------
def t_resolve_mp3_youtube_url():
    print("-- resolve_mp3_youtube_url: breaker, scoring, watch URL --")
    orig_brk, orig_search, orig_dur = (yds._yt_breaker_open,
                                      yds._yt_search_entries,
                                      yds._expected_duration)
    try:
        yds._yt_breaker_open = lambda: True
        yds._yt_search_entries = lambda q, n=5: (_ for _ in ()).throw(
            AssertionError("search must not run when breaker open"))
        check("breaker open → None", yds.resolve_mp3_youtube_url("A", "S") is None)

        yds._yt_breaker_open = lambda: False
        yds._expected_duration = lambda a, s: 200
        yds._yt_search_entries = lambda q, n=5: [
            {"title": "A - S (Official Audio)", "uploader": "A",
             "duration": 200, "url": "VIDID12345"},
            {"title": "A - S (8D slowed + reverb)", "uploader": "fan",
             "duration": 200, "url": "BADID12345"},
        ]
        url = yds.resolve_mp3_youtube_url("A", "S")
        check("best candidate picked as watch URL",
              url == "https://www.youtube.com/watch?v=VIDID12345")

        yds._yt_search_entries = lambda q, n=5: []
        check("no candidates → None",
              yds.resolve_mp3_youtube_url("A", "S") is None)

        yds._yt_search_entries = lambda q, n=5: (_ for _ in ()).throw(
            RuntimeError("boom"))
        check("never raises", yds.resolve_mp3_youtube_url("A", "S") is None)
    finally:
        yds._yt_breaker_open, yds._yt_search_entries, yds._expected_duration = (
            orig_brk, orig_search, orig_dur)


# --------------------------------- _mp3_try_worker ------------------------
def t_mp3_try_worker():
    print("-- _mp3_try_worker: posts audio JOB, bails cleanly --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig_send, orig_resolve = svc._api_send_message, yds.resolve_mp3_youtube_url
    posted = []
    svc._api_send_message = lambda token, chat_id, text: (
        posted.append(text) or True)
    try:
        bot = FakeBot()
        # bridge disabled
        r2 = _with_env(WORKER_CHANNEL_ID="")
        check("disabled → False",
              handlers._mp3_try_worker(bot, 42, 7, "A", "S", "A - S") is False)
        r2()
        check("no JOB when disabled", posted == [])

        # no URL resolved
        yds.resolve_mp3_youtube_url = lambda a, s: None
        check("no URL → False",
              handlers._mp3_try_worker(bot, 42, 7, "A", "S", "A - S") is False)

        # happy path
        yds.resolve_mp3_youtube_url = lambda a, s: "https://youtu.be/abc123"
        ok = handlers._mp3_try_worker(bot, 42, 7, "A", "S", "A - S")
        check("audio job posted → True", ok is True)
        import json as _json
        payload = _json.loads(posted[0][4:])
        check("JOB kind=audio with artist/song",
              payload.get("kind") == "audio"
              and payload.get("artist") == "A"
              and payload.get("song") == "S")
        check("silent handoff: no home-downloader chatter",
              not any("🏠 Home downloader is on it" in t
                      for _, t in bot.sent))
    finally:
        svc._api_send_message, yds.resolve_mp3_youtube_url = orig_send, orig_resolve
        restore()


# --------------------------------- channel_post: DONE audio ---------------
def _audio_job(jid="au1"):
    svc._job_update(jid, {"job_id": jid, "chat_id": 42, "user_id": 7,
                          "video_url": "https://youtu.be/abc",
                          "title": "A - S", "kind": "audio",
                          "artist": "A", "song": "S",
                          "ts": time.time(), "status": "pending"})


def t_channel_post_done_audio():
    print("-- DONE audio → copyMessage + file_id cached --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    _audio_job()
    bot = FakeBot(sent_file_id="NEWFID")
    noted = []
    orig_note = yds.note_mp3_file_id
    yds.note_mp3_file_id = lambda a, s, fid: noted.append((a, s, fid))
    try:
        upd = FakeUpdate()
        upd.channel_post = FakePost("DONE au1 555", -1001)
        handlers.worker_channel_post(upd, FakeContext(bot=bot))
        check("copyMessage called", len(bot.copies) == 1
              and bot.copies[0]["chat_id"] == 42)
        check("file_id cached for instant repeats",
              noted == [("A", "S", "NEWFID")])
        check("job marked done",
              svc._load_jobs()["au1"]["status"] == "done")
    finally:
        yds.note_mp3_file_id = orig_note
        restore()


def t_channel_post_fail_audio_permanent():
    print("-- FAIL audio_too_long → honest notice, no local download --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    _audio_job("au2")
    bot = FakeBot()
    ran = []
    orig_thread = handlers._mp3_local_fallback_thread
    handlers._mp3_local_fallback_thread = lambda *a: ran.append(a)
    try:
        import threading as _th
        orig_T = _th.Thread
        _th.Thread = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("no thread on permanent fail"))
        try:
            upd = FakeUpdate()
            upd.channel_post = FakePost("FAIL au2 audio_too_long", -1001)
            handlers.worker_channel_post(upd, FakeContext(bot=bot))
        finally:
            _th.Thread = orig_T
        check("honest track notice sent",
              any("Track Too Long" in t for _, t in bot.sent))
        check("no local fallback on permanent fail", ran == [])
    finally:
        handlers._mp3_local_fallback_thread = orig_thread
        restore()


def t_channel_post_fail_audio_transient():
    print("-- FAIL audio (transient) → snag notice + local fallback thread --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    _audio_job("au3")
    bot = FakeBot()
    started = []
    import threading as _th
    orig_T = _th.Thread

    class FakeThread:
        def __init__(self, target=None, args=(), **kw):
            self._target, self._args = target, args

        def start(self):
            started.append((self._target, self._args))

    _th.Thread = FakeThread
    try:
        upd = FakeUpdate()
        upd.channel_post = FakePost("FAIL au3 error", -1001)
        handlers.worker_channel_post(upd, FakeContext(bot=bot))
        check("silent fallback: no snag chatter",
              not any("hit a snag" in t for _, t in bot.sent))
        check("fallback thread started",
              len(started) == 1
              and started[0][0] is handlers._mp3_local_fallback_thread
              and started[0][1][1:4] == (42, 7, "A"))
    finally:
        _th.Thread = orig_T
        restore()


# --------------------------------- timeout tick: audio --------------------
def t_worker_timeout_tick_audio():
    print("-- worker_timeout_tick: expired audio job → mp3 fallback --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    svc._job_update("au9", {"job_id": "au9", "chat_id": 42, "user_id": 7,
                            "video_url": "https://youtu.be/abc",
                            "kind": "audio", "artist": "A", "song": "S",
                            "ts": time.time() - 9999, "status": "pending"})
    bot = FakeBot()
    calls = []
    orig = handlers._deliver_mp3_after_worker_fail
    handlers._deliver_mp3_after_worker_fail = (
        lambda b, e, fail_code=None: calls.append((e.get("job_id"), fail_code)))
    try:
        handlers.worker_timeout_tick(bot)
        check("mp3 fallback invoked with timeout",
              calls == [("au9", "timeout")])
    finally:
        handlers._deliver_mp3_after_worker_fail = orig
        restore()


# --------------------------------- _deliver_mp3_after_worker_fail ---------
def t_deliver_mp3_after_worker_fail():
    print("-- _deliver_mp3_after_worker_fail: honest vs threaded --")
    bot = FakeBot()
    entry = {"chat_id": 42, "user_id": 7, "artist": "A", "song": "S"}
    handlers._deliver_mp3_after_worker_fail(bot, dict(entry),
                                            fail_code="audio_too_large")
    check("audio_too_large → honest notice",
          any("50MB" in t and "track" in t.lower() for _, t in bot.sent))

    bot2 = FakeBot()
    import threading as _th
    orig_T = _th.Thread
    started = []

    class FakeThread:
        def __init__(self, target=None, args=(), **kw):
            self._target, self._args = target, args

        def start(self):
            started.append(self._args)

    _th.Thread = FakeThread
    try:
        handlers._deliver_mp3_after_worker_fail(bot2, dict(entry),
                                                fail_code="error")
    finally:
        _th.Thread = orig_T
    check("transient → silent (no snag chatter)",
          not any("hit a snag" in t for _, t in bot2.sent))
    check("transient → fallback thread with artist/song",
          started and started[0][3:5] == ("A", "S"))


TESTS = [
    t_post_job_audio_kind,
    t_honest_audio_msgs,
    t_mp3_cached_lookup,
    t_resolve_mp3_youtube_url,
    t_mp3_try_worker,
    t_channel_post_done_audio,
    t_channel_post_fail_audio_permanent,
    t_channel_post_fail_audio_transient,
    t_worker_timeout_tick_audio,
    t_deliver_mp3_after_worker_fail,
]

if __name__ == "__main__":
    for t in TESTS:
        try:
            t()
        except Exception as e:
            FAIL += 1
            FAILURES.append(f"{t.__name__} raised {type(e).__name__}: {e}")
            print(f"  FAIL {t.__name__} raised {type(e).__name__}: {e}")
    print("=" * 50)
    print(f"PASS: {PASS}   FAIL: {FAIL}")
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print(f"  - {f}")
    else:
        print("all green ✅")
    sys.exit(1 if FAIL else 0)
