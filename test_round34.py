"""Round 34 — home-worker bridge wiring (server side).

Covers the handlers.py/bot.py integration: worker-first /download,
channel-post DONE/FAIL handling, and the timeout tick's local fallback.
Service-module logic itself is covered by home-worker/test_home_worker.py.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from services import home_worker_service as svc

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


class FakeProcessing:
    def __init__(self):
        self.edits = []

    def edit_text(self, text):
        self.edits.append(text)


class FakeMessage:
    def __init__(self, processing=None):
        self.processing = processing or FakeProcessing()
        self.replies = []

    def reply_text(self, text, **kw):
        self.replies.append(text)
        return self.processing

    def reply_video(self, *a, **kw):
        self.replies.append("<video>")


class FakeChat:
    def __init__(self, id):
        self.id = id


class FakeUser:
    def __init__(self, id):
        self.id = id


class FakeUpdate:
    def __init__(self, chat_id=42, user_id=7, args=None):
        self.effective_chat = FakeChat(chat_id)
        self.effective_user = FakeUser(user_id)
        self.message = FakeMessage()
        self.channel_post = None


class FakeContext:
    def __init__(self, args=None, bot=None):
        self.args = args or []
        self.bot = bot or FakeBot()


class FakeBot:
    def __init__(self):
        self.sent = []
        self.copies = []
        self.videos = []

    def send_message(self, chat_id=None, text=None, **kw):
        self.sent.append((chat_id, text))

    def copy_message(self, chat_id=None, from_chat_id=None,
                     message_id=None, caption=None):
        self.copies.append({"chat_id": chat_id, "from_chat_id": from_chat_id,
                            "message_id": message_id, "caption": caption})

    def send_video(self, chat_id=None, video=None, caption=None, **kw):
        self.videos.append((chat_id, caption))


class FakePost:
    def __init__(self, text, chat_id):
        self.text = text
        self.chat = FakeChat(chat_id)


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


def _fake_video_file():
    """A real (empty) temp file so _deliver_video_local's open() works."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    return path


# --------------------------------- download_command: worker-first ---------
def t_download_worker_first():
    print("-- download_command posts JOB and returns early when enabled --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    calls = []
    orig_send = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: (
        calls.append((token, chat_id, text)) or True)
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (_ for _ in ()).throw(
        AssertionError("local path must not run"))
    try:
        upd = FakeUpdate(chat_id=42, user_id=7)
        ctx = FakeContext(args=["https://youtu.be/abc123"])
        handlers.download_command(upd, ctx)
        check("JOB posted to worker channel",
              calls and calls[0][1] == -1001
              and calls[0][2].startswith("JOB "))
        check("JOB posted with MAIN token", calls and calls[0][0] == "main")
        edits = upd.message.processing.edits
        check("silent handoff: no home-downloader chatter",
              edits == [])
        check("job recorded pending",
              sum(1 for e in svc._load_jobs().values()
                  if e.get("status") == "pending") == 1)
    finally:
        svc._api_send_message = orig_send
        handlers.download_youtube_video = orig_dl
        restore()


def t_download_worker_disabled_falls_through():
    print("-- download_command uses local path when bridge disabled --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="", TELEGRAM_TOKEN="main")
    ran = []
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (
        ran.append(url) or (True, (_fake_video_file(), "done")))
    orig_cleanup = handlers.cleanup_video
    handlers.cleanup_video = lambda p: None
    try:
        upd = FakeUpdate(chat_id=42, user_id=7)
        ctx = FakeContext(args=["https://youtu.be/abc123"],
                          bot=FakeBot())
        handlers.download_command(upd, ctx)
        check("local download ran", ran == ["https://youtu.be/abc123"])
        check("video delivered locally", "<video>" in upd.message.replies)
    finally:
        handlers.download_youtube_video = orig_dl
        handlers.cleanup_video = orig_cleanup
        restore()


def t_download_post_job_failure_falls_through():
    print("-- download_command falls through when JOB post fails --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: False
    ran = []
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (
        ran.append(url) or (False, "😕 nope"))
    try:
        upd = FakeUpdate(chat_id=42, user_id=7)
        ctx = FakeContext(args=["https://youtu.be/abc123"], bot=FakeBot())
        handlers.download_command(upd, ctx)
        check("local path used after post_job failure",
              ran == ["https://youtu.be/abc123"])
        check("failure notice shown",
              upd.message.processing.edits
              and upd.message.processing.edits[0] == "😕 nope")
    finally:
        svc._api_send_message = orig_send
        handlers.download_youtube_video = orig_dl
        restore()


# --------------------------------- worker_channel_post ------------------
def _done_update(job_id, message_id, chat_id=-1001):
    upd = FakeUpdate()
    upd.channel_post = FakePost("DONE %s %d" % (job_id, message_id), chat_id)
    return upd


def t_channel_post_done_copies():
    print("-- DONE signal → copyMessage delivery --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    svc._job_update("job1", {"job_id": "job1", "chat_id": 42, "user_id": 7,
                             "url": "https://youtu.be/abc",
                             "ts": time.time(), "status": "pending"})
    bot = FakeBot()
    try:
        handlers.worker_channel_post(_done_update("job1", 555),
                                     FakeContext(bot=bot))
        check("copyMessage called once", len(bot.copies) == 1)
        c = bot.copies[0]
        check("copy targets user chat", c["chat_id"] == 42)
        check("copy reads worker channel",
              c["from_chat_id"] == -1001 and c["message_id"] == 555)
        check("job marked done",
              svc._load_jobs()["job1"]["status"] == "done")
    finally:
        restore()


def t_channel_post_ignores_noise():
    print("-- channel_post ignores noise --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    bot = FakeBot()
    try:
        # wrong channel
        handlers.worker_channel_post(_done_update("x", 1, chat_id=-999),
                                     FakeContext(bot=bot))
        # JOB echo
        upd = FakeUpdate()
        upd.channel_post = FakePost('JOB {"job_id":"x"}', -1001)
        handlers.worker_channel_post(upd, FakeContext(bot=bot))
        # human chatter
        upd2 = FakeUpdate()
        upd2.channel_post = FakePost("hello everyone", -1001)
        handlers.worker_channel_post(upd2, FakeContext(bot=bot))
        # malformed DONE
        upd3 = FakeUpdate()
        upd3.channel_post = FakePost("DONE onlyonepart", -1001)
        handlers.worker_channel_post(upd3, FakeContext(bot=bot))
        # no channel_post at all
        handlers.worker_channel_post(FakeUpdate(), FakeContext(bot=bot))
        check("no copies for noise", bot.copies == [])
        check("no fallback sends for noise", bot.sent == [])
    finally:
        restore()


def t_channel_post_fail_falls_back():
    print("-- FAIL signal → local fallback --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    svc._job_update("job9", {"job_id": "job9", "chat_id": 42, "user_id": 7,
                             "url": "https://youtu.be/long",
                             "ts": time.time(), "status": "pending"})
    bot = FakeBot()
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (_ for _ in ()).throw(
        AssertionError("permanent fail must not download"))
    try:
        upd = FakeUpdate()
        upd.channel_post = FakePost("FAIL job9 too_long", -1001)
        handlers.worker_channel_post(upd, FakeContext(bot=bot))
        check("honest too_long notice sent",
              bot.sent and "Max duration: 10 minutes." in bot.sent[0][1])
        check("job marked failed",
              svc._load_jobs()["job9"]["status"] == "failed")
    finally:
        handlers.download_youtube_video = orig_dl
        restore()


def t_channel_post_copyfail_falls_back():
    print("-- copyMessage failure → local fallback --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    svc._job_update("job2", {"job_id": "job2", "chat_id": 42, "user_id": 7,
                             "url": "https://youtu.be/abc",
                             "ts": time.time(), "status": "pending"})

    class BadCopy(FakeBot):
        def copy_message(self, **kw):
            raise Exception("deleted")

    bot = BadCopy()
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (
        True, (_fake_video_file(), "🎉 Here's your video!"))
    orig_cleanup = handlers.cleanup_video
    handlers.cleanup_video = lambda p: None
    try:
        handlers.worker_channel_post(_done_update("job2", 777),
                                     FakeContext(bot=bot))
        check("local fallback delivered after COPYFAIL", bot.videos != [])
    finally:
        handlers.download_youtube_video = orig_dl
        handlers.cleanup_video = orig_cleanup
        restore()


# --------------------------------- worker_timeout_tick ------------------
def t_timeout_tick_expires_and_falls_back():
    print("-- timeout tick expires stale jobs --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="-1001")
    old = time.time() - (svc._WORKER_TIMEOUT_SECS + 10)
    svc._job_update("old1", {"job_id": "old1", "chat_id": 42, "user_id": 7,
                             "url": "https://youtu.be/abc",
                             "ts": old, "status": "pending"})
    svc._job_update("new1", {"job_id": "new1", "chat_id": 42, "user_id": 7,
                             "url": "https://youtu.be/def",
                             "ts": time.time(), "status": "pending"})
    bot = FakeBot()
    orig_dl = handlers.download_youtube_video
    handlers.download_youtube_video = lambda url: (
        True, (_fake_video_file(), "🎉 Here's your video!"))
    orig_cleanup = handlers.cleanup_video
    handlers.cleanup_video = lambda p: None
    try:
        handlers.worker_timeout_tick(bot)
        jobs = svc._load_jobs()
        check("stale job expired", jobs["old1"]["status"] == "expired")
        check("fresh job still pending", jobs["new1"]["status"] == "pending")
        check("fallback delivered for stale job", bot.videos != [])
    finally:
        handlers.download_youtube_video = orig_dl
        handlers.cleanup_video = orig_cleanup
        restore()


def t_timeout_tick_disabled_noop():
    print("-- timeout tick is a no-op when bridge disabled --")
    _fresh_store()
    restore = _with_env(WORKER_CHANNEL_ID="")
    bot = FakeBot()
    try:
        handlers.worker_timeout_tick(bot)  # must not raise
        check("no crash when disabled", True)
        check("nothing delivered", bot.videos == [] and bot.sent == [])
    finally:
        restore()


if __name__ == "__main__":
    for fn in [t_download_worker_first,
               t_download_worker_disabled_falls_through,
               t_download_post_job_failure_falls_through,
               t_channel_post_done_copies,
               t_channel_post_ignores_noise,
               t_channel_post_fail_falls_back,
               t_channel_post_copyfail_falls_back,
               t_timeout_tick_expires_and_falls_back,
               t_timeout_tick_disabled_noop]:
        fn()
    print("=" * 50)
    print(f"round-34: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print("  -", f)
    sys.exit(1 if FAIL else 0)
