"""Round-37 tests: the home worker resolves YouTube itself + liveness.

The streamer now survives a server-side YouTube block wave: audio jobs
go out with artist/song (+ an optional URL hint), and the worker runs
its own ytsearch over the home connection. Server side:
- post_job(..., kind="audio") accepts url="" + expected_dur
- _mp3_try_worker posts even when resolve_mp3_youtube_url() is empty
  (block wave) — the worker resolves instead of falling back to Audius
- worker heartbeat: note_heartbeat/last_heartbeat/worker_alive; the
  channel handler records "HB <ts>" posts; a stale heartbeat makes the
  bot skip the worker instantly (no 4-minute stall)
- _score_candidate hard-rejects "inspired by"/tribute tracks (the
  2026-09-25 wrong-song incident), unless the song itself has the marker
"""
import json
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


def _fresh_stores():
    tmp = tempfile.mkdtemp()
    svc._JOB_STORE = os.path.join(tmp, "worker_jobs.json")
    svc._HB_STORE = os.path.join(tmp, "worker_heartbeat.json")
    return tmp


class FakeBot:
    def __init__(self):
        self.sent = []
        self.copies = []

    def send_message(self, chat_id=None, text=None, **kw):
        self.sent.append((chat_id, text))


class FakePost:
    def __init__(self, text, chat_id):
        self.text = text
        self.chat = type("C", (), {"id": chat_id})()


class FakeUpdate:
    channel_post = None


class FakeContext:
    def __init__(self, bot):
        self.bot = bot


# ------------------------------------------------- heartbeat --------------
def t_heartbeat_tracking():
    print("-- heartbeat: note/last/alive --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    try:
        check("no heartbeat ever → alive (fresh install)",
              svc.worker_alive() is True)
        svc.note_heartbeat()
        check("recent heartbeat → alive", svc.worker_alive() is True)
        check("last_heartbeat recorded",
              abs(svc.last_heartbeat() - time.time()) < 5)
        svc.note_heartbeat(time.time() - 600)
        check("stale heartbeat (10 min) → not alive",
              svc.worker_alive() is False)
    finally:
        restore()


def t_heartbeat_disabled_bridge():
    print("-- heartbeat: disabled bridge → not alive --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="")
    try:
        svc.note_heartbeat()
        check("disabled bridge → worker_alive False",
              svc.worker_alive() is False)
    finally:
        restore()


def t_channel_post_records_heartbeat():
    print("-- worker_channel_post: HB posts recorded silently --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    bot = FakeBot()
    try:
        upd = FakeUpdate()
        upd.channel_post = FakePost("HB %d" % int(time.time()), -1001)
        handlers.worker_channel_post(upd, FakeContext(bot=bot))
        check("heartbeat recorded",
              abs(svc.last_heartbeat() - time.time()) < 5)
        check("no user message sent", bot.sent == [])
        check("no copy attempted", bot.copies == [])
        # Malformed HB must not crash.
        upd2 = FakeUpdate()
        upd2.channel_post = FakePost("HB nonsense", -1001)
        handlers.worker_channel_post(upd2, FakeContext(bot=bot))
        check("malformed HB tolerated",
              abs(svc.last_heartbeat() - time.time()) < 5)
    finally:
        restore()


# ------------------------------------------------- url-less audio jobs ----
def t_post_job_audio_no_url():
    print("-- post_job: audio without URL + expected_dur --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig = svc._api_send_message
    posted = []
    svc._api_send_message = lambda token, chat_id, text: (
        posted.append(text) or True)
    try:
        jid = svc.post_job(42, 7, "", title="A - S", kind="audio",
                           artist="A", song="S", expected_dur=200)
        check("job posted", bool(jid))
        payload = json.loads(posted[0][4:])
        check("payload video_url empty", payload.get("video_url") == "")
        check("payload carries expected_dur",
              payload.get("expected_dur") == 200)
        check("payload carries requested_at",
              abs(payload.get("requested_at", 0) - time.time()) < 5)
        check("payload kind=audio", payload.get("kind") == "audio")
    finally:
        svc._api_send_message = orig
        restore()


def t_mp3_try_worker_posts_without_url():
    print("-- _mp3_try_worker: block wave → still posts (worker resolves) --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    orig_resolve = yds.resolve_mp3_youtube_url
    orig_dur = yds.mp3_expected_duration
    posted = []
    svc._api_send_message = lambda token, chat_id, text: (
        posted.append(text) or True)
    yds.resolve_mp3_youtube_url = lambda a, s: None  # block wave
    yds.mp3_expected_duration = lambda a, s: 303
    try:
        bot = FakeBot()
        ok = handlers._mp3_try_worker(bot, 42, 7, "Billie Eilish", "CHIHIRO",
                                      "Billie Eilish - CHIHIRO")
        check("posts even with no URL hint → True", ok is True)
        payload = json.loads(posted[0][4:])
        check("JOB has empty video_url (worker resolves)",
              payload.get("video_url") == "")
        check("JOB carries artist/song/expected_dur",
              payload.get("artist") == "Billie Eilish"
              and payload.get("song") == "CHIHIRO"
              and payload.get("expected_dur") == 303)
        check("silent handoff (no chatter)",
              not any("🏠" in (t or "") for _, t in bot.sent))
    finally:
        (svc._api_send_message, yds.resolve_mp3_youtube_url,
         yds.mp3_expected_duration) = orig_send, orig_resolve, orig_dur
        restore()


def t_mp3_try_worker_skips_dead_streamer():
    print("-- _mp3_try_worker: stale heartbeat → instant local path --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    posted = []
    svc._api_send_message = lambda token, chat_id, text: (
        posted.append(text) or True)
    svc.note_heartbeat(time.time() - 600)  # streamer died 10 min ago
    try:
        bot = FakeBot()
        ok = handlers._mp3_try_worker(bot, 42, 7, "A", "S", "A - S")
        check("dead streamer → False (no 4-min stall)", ok is False)
        check("nothing posted", posted == [])
    finally:
        svc._api_send_message = orig_send
        restore()


def t_mp3_try_worker_hint_used_when_available():
    print("-- _mp3_try_worker: URL hint passed through when resolvable --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    orig_resolve = yds.resolve_mp3_youtube_url
    orig_dur = yds.mp3_expected_duration
    posted = []
    svc._api_send_message = lambda token, chat_id, text: (
        posted.append(text) or True)
    yds.resolve_mp3_youtube_url = lambda a, s: "https://youtu.be/abc123"
    yds.mp3_expected_duration = lambda a, s: None
    try:
        bot = FakeBot()
        ok = handlers._mp3_try_worker(bot, 42, 7, "A", "S", "A - S")
        payload = json.loads(posted[0][4:])
        check("hint URL passed through",
              ok is True and payload.get("video_url")
              == "https://youtu.be/abc123")
    finally:
        (svc._api_send_message, yds.resolve_mp3_youtube_url,
         yds.mp3_expected_duration) = orig_send, orig_resolve, orig_dur
        restore()


# ------------------------------------------------- scoring ---------------
def t_score_rejects_inspired_by():
    print('-- _score_candidate: "inspired by" / tribute rejected --')
    s = yds._score_candidate("Echoes of Chihiro | Inspired by Billie Eilish",
                             "AT PLAYER", 228,
                             "Billie Eilish", "CHIHIRO", 303)
    check("inspired-by imitation rejected", s <= -1e8)
    s2 = yds._score_candidate("Chihiro — A Tribute to Billie Eilish",
                              "Tribute Band", 200,
                              "Billie Eilish", "CHIHIRO", 303)
    check("tribute rejected", s2 <= -1e8)
    s3 = yds._score_candidate("Tenacious D - Tribute (Official Video)",
                              "TenaciousD", 240,
                              "Tenacious D", "Tribute", 240)
    check("song genuinely titled Tribute untouched", s3 > -1e8)
    s4 = yds._score_candidate("Billie Eilish - CHIHIRO (Official Audio)",
                              "BillieEilish", 303,
                              "Billie Eilish", "CHIHIRO", 303)
    check("official upload still scores well", s4 > 50)


def t_build_copy_params_audio_caption():
    print("-- build_copy_params: audio gets the MP3 caption --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    try:
        jobs = {"ja": {"chat_id": 42, "kind": "audio", "status": "pending"},
                "jv": {"chat_id": 42, "kind": "video", "status": "pending"}}
        with open(svc._JOB_STORE, "w") as f:
            json.dump(jobs, f)
        pa = svc.build_copy_params("ja", 111)
        pv = svc.build_copy_params("jv", 222)
        check("audio delivery captioned as MP3",
              pa is not None and pa.get("caption") == "🎧 Here's your MP3!")
        check("video caption untouched",
              pv is not None and pv.get("caption") == svc.COPY_CAPTION)
    finally:
        restore()


def t_mp3_expected_duration_wrapper():
    print("-- mp3_expected_duration wrapper --")
    orig = yds._expected_duration
    yds._expected_duration = lambda a, s: 200
    try:
        check("wrapper passes through", yds.mp3_expected_duration("A", "S")
              == 200)
    finally:
        yds._expected_duration = orig
    orig2 = yds._expected_duration
    def boom(a, s):
        raise RuntimeError("net down")
    yds._expected_duration = boom
    try:
        check("wrapper never raises", yds.mp3_expected_duration("A", "S")
              is None)
    finally:
        yds._expected_duration = orig2


TESTS = [
    t_heartbeat_tracking,
    t_heartbeat_disabled_bridge,
    t_channel_post_records_heartbeat,
    t_post_job_audio_no_url,
    t_mp3_try_worker_posts_without_url,
    t_mp3_try_worker_skips_dead_streamer,
    t_mp3_try_worker_hint_used_when_available,
    t_score_rejects_inspired_by,
    t_mp3_expected_duration_wrapper,
    t_build_copy_params_audio_caption,
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
