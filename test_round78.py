#!/usr/bin/env python3
"""Round-78 tests: video delivery mirrors the MP3 self-cleaning status.

Round 75 gave the MP3 flow one self-cleaning status message; the video
(/download) flow was deliberately untouched — its "Downloading…" status
survived successful delivery (user screenshot, 2026-09-26). This round
extends the same contract to all four video paths:

- local success      → status deleted after the video lands
- worker DONE        → status deleted after copyMessage
- block-wave queue   → status edited into the queued notice (no stacking);
                       retry tick deletes it on auto-delivery, edits it on
                       honest failure / gave-up
- timeout fallback   → status deleted on local delivery, carried on re-queue

Helpers never raise; delete/edit failures never mask a delivery; parallel
requests keep separate statuses (per-message ids throughout).
"""
import json
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from handlers import (
    _mp3_status_delete,
    _mp3_status_update,
    download_command,
    video_retry_tick,
    worker_channel_post,
    _deliver_video_local,
)
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
    yds._MP3_RETRY_JSON = os.path.join(tmp, "mp3_retry.json")
    yds._VIDEO_RETRY_JSON = os.path.join(tmp, "video_retry.json")
    return tmp


class FakeBot:
    """Records bot API calls. fail_delete/fail_edit simulate a gone message."""

    def __init__(self, fail_delete=False, fail_edit=False, fail_video=False):
        self.calls = []
        self.fail_delete = fail_delete
        self.fail_edit = fail_edit
        self.fail_video = fail_video
        self._next_id = 1000

    def _new_msg(self):
        self._next_id += 1
        return types.SimpleNamespace(message_id=self._next_id)

    def send_message(self, chat_id, text, **kw):
        self.calls.append(("send_message", chat_id, text))
        return self._new_msg()

    def edit_message_text(self, chat_id, message_id, text, **kw):
        if self.fail_edit:
            raise RuntimeError("message gone")
        self.calls.append(("edit", chat_id, message_id, text))

    def delete_message(self, chat_id, message_id):
        if self.fail_delete:
            raise RuntimeError("message gone")
        self.calls.append(("delete", chat_id, message_id))

    def send_video(self, chat_id, video, caption=None, **kw):
        if self.fail_video:
            raise RuntimeError("too large")
        self.calls.append(("send_video", chat_id, caption))
        return self._new_msg()

    def copy_message(self, chat_id, from_chat_id, message_id, caption=None,
                     **kw):
        self.calls.append(("copy_message", chat_id, caption))
        return self._new_msg()


class FakeStatus:
    """The 'Downloading…' message: records edits, exposes message_id."""

    def __init__(self, bot, chat_id, message_id=501):
        self._bot = bot
        self._chat_id = chat_id
        self.message_id = message_id

    def edit_text(self, text, **kw):
        self._bot.edit_message_text(chat_id=self._chat_id,
                                    message_id=self.message_id, text=text)


class FakeMessage:
    def __init__(self, bot, chat_id=9, fail_video=False):
        self._bot = bot
        self._chat_id = chat_id
        self._fail_video = fail_video
        self.status = None

    def reply_text(self, text, **kw):
        self._bot.calls.append(("send_message", self._chat_id, text))
        self.status = FakeStatus(self._bot, self._chat_id)
        return self.status

    def reply_video(self, video_file, caption=None, **kw):
        if self._fail_video:
            raise RuntimeError("too large")
        self._bot.calls.append(("send_video", self._chat_id, caption))


def _call_types(bot):
    return [c[0] for c in bot.calls]


def _updates(bot, chat_id=9, fail_video=False, args=None):
    msg = FakeMessage(bot, chat_id, fail_video=fail_video)
    update = types.SimpleNamespace(
        message=msg,
        effective_user=types.SimpleNamespace(id=7),
        effective_chat=types.SimpleNamespace(id=chat_id))
    context = types.SimpleNamespace(bot=bot,
                                    args=args if args is not None
                                    else ["https://youtu.be/abc123"])
    return update, context, msg


def _stub_downloads(monkey, success=True, wave=False):
    """Stub the module-level seams download_command touches."""
    fd, real_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    monkey.append(("handlers", "download_youtube_video",
                   lambda url: (True, (real_path, "info")) if success
                   else (False, "genuine failure")))
    monkey.append(("handlers", "validate_youtube_url", lambda url: True))
    monkey.append(("handlers", "cleanup_video", lambda p: None))


def _apply(monkey):
    applied = []
    for mod_name, attr, val in monkey:
        mod = {"handlers": handlers, "svc": svc, "yds": yds}[mod_name]
        applied.append((mod, attr, getattr(mod, attr)))
        setattr(mod, attr, val)
    return applied


def _restore(applied):
    for mod, attr, val in applied:
        setattr(mod, attr, val)


# ------------------------------------------------------- local success path

def t_local_success_deletes_status():
    print("-- local success: status deleted after the video lands --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=True)
    monkey.append(("svc", "worker_enabled", lambda: False))
    monkey.append(("svc", "worker_alive", lambda: False))
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        update, context, msg = _updates(bot)
        download_command(update, context)
    finally:
        _restore(applied)
    check("video sent", "send_video" in _call_types(bot))
    check("status deleted", ("delete", 9, 501) in bot.calls)
    check("status not edited into info line",
          not [c for c in bot.calls
               if c[0] == "edit" and c[2] == 501])


def t_local_success_delete_failure_ok():
    print("-- local success: delete failure never masks delivery --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=True)
    monkey.append(("svc", "worker_enabled", lambda: False))
    monkey.append(("svc", "worker_alive", lambda: False))
    applied = _apply(monkey)
    bot = FakeBot(fail_delete=True)
    try:
        update, context, msg = _updates(bot)
        download_command(update, context)  # must not raise
    finally:
        _restore(applied)
    check("video still sent", "send_video" in _call_types(bot))


def t_local_send_failure_keeps_honest_notice():
    print("-- local send failure: honest notice edits status, no delete --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=True)
    monkey.append(("svc", "worker_enabled", lambda: False))
    monkey.append(("svc", "worker_alive", lambda: False))
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        update, context, msg = _updates(bot, fail_video=True)
        download_command(update, context)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 501]
    check("status edited into too-large notice",
          len(edits) == 1 and "too large" in edits[0][3])
    check("nothing deleted", "delete" not in _call_types(bot))


def t_invalid_url_keeps_honest_notice():
    print("-- invalid URL: honest notice edits status, no delete --")
    _fresh_stores()
    monkey = [("handlers", "validate_youtube_url", lambda url: False)]
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        update, context, msg = _updates(bot)
        download_command(update, context)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 501]
    check("status edited into invalid-URL notice",
          len(edits) == 1 and "Invalid YouTube URL" in edits[0][3])
    check("nothing deleted", "delete" not in _call_types(bot))


# ------------------------------------------------------------- wave → queue

def t_wave_queue_edits_status_and_tracks_id():
    print("-- block wave: status edited into queued notice, id tracked --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=False)
    monkey.append(("svc", "worker_enabled", lambda: False))
    monkey.append(("svc", "worker_alive", lambda: False))
    monkey.append(("yds", "mp3_block_wave_active", lambda: True))
    monkey.append(("yds", "download_hit_block_wave", lambda: True))
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        update, context, msg = _updates(bot)
        download_command(update, context)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 501]
    check("one edit into queued notice (no stacking)",
          len(edits) == 1 and "queued" in edits[0][3])
    with open(yds._VIDEO_RETRY_JSON, encoding="utf-8") as f:
        data = json.load(f)
    entries = list(data.values())
    check("queue entry tracks the status id",
          len(entries) == 1 and entries[0].get("status_msg_id") == 501)


# ------------------------------------------------------------- worker path

def t_handoff_passes_status_id():
    print("-- worker handoff: status_msg_id rides on the job --")
    _fresh_stores()
    restore_env = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    monkey = [("svc", "worker_enabled", lambda: True),
              ("svc", "worker_alive", lambda: True)]
    applied = _apply(monkey)
    orig_api = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    seen = {}
    orig_post = svc.post_job

    def spy_post(chat_id, user_id, url, **kw):
        seen.update(kw)
        return orig_post(chat_id, user_id, url, **kw)

    svc.post_job = spy_post
    bot = FakeBot()
    try:
        update, context, msg = _updates(bot)
        download_command(update, context)
    finally:
        svc.post_job = orig_post
        svc._api_send_message = orig_api
        _restore(applied)
        restore_env()
    check("post_job got the status id", seen.get("status_msg_id") == 501)
    check("status left up during handoff (deleted on DONE)",
          "delete" not in _call_types(bot))


def t_worker_done_video_deletes_status():
    print("-- worker DONE (video): status deleted after copy --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-10099", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    bot = FakeBot()
    try:
        jid = svc.post_job(42, 7, "https://youtu.be/abc",
                           kind="video", status_msg_id=777)
        update = types.SimpleNamespace(
            channel_post=types.SimpleNamespace(
                text=f"DONE {jid} 12345",
                chat=types.SimpleNamespace(id=-10099)))
        context = types.SimpleNamespace(bot=bot)
        worker_channel_post(update, context)
    finally:
        svc._api_send_message = orig_send
        restore()
    check("copy delivered", "copy_message" in _call_types(bot))
    check("status deleted", ("delete", 42, 777) in bot.calls)


def t_worker_done_video_delete_failure_ok():
    print("-- worker DONE (video): delete failure never breaks the loop --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-10098", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    bot = FakeBot(fail_delete=True)
    try:
        jid = svc.post_job(42, 7, "https://youtu.be/abc",
                           kind="video", status_msg_id=777)
        update = types.SimpleNamespace(
            channel_post=types.SimpleNamespace(
                text=f"DONE {jid} 12345",
                chat=types.SimpleNamespace(id=-10098)))
        context = types.SimpleNamespace(bot=bot)
        worker_channel_post(update, context)  # must not raise
    finally:
        svc._api_send_message = orig_send
        restore()
    check("copy still delivered", "copy_message" in _call_types(bot))


# ------------------------------------------------------- timeout fallback

def t_fallback_success_deletes_status():
    print("-- timeout fallback: local delivery deletes the status --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=True)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        _deliver_video_local(bot, 9, 7, "https://youtu.be/abc",
                             status_msg_id=555)
    finally:
        _restore(applied)
    check("video sent", "send_video" in _call_types(bot))
    check("status deleted", ("delete", 9, 555) in bot.calls)


def t_fallback_wave_carries_status_id():
    print("-- timeout fallback: re-queue carries the status id --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=False)
    monkey.append(("yds", "mp3_block_wave_active", lambda: True))
    monkey.append(("yds", "download_hit_block_wave", lambda: True))
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        _deliver_video_local(bot, 9, 7, "https://youtu.be/abc",
                             status_msg_id=555)
    finally:
        _restore(applied)
    with open(yds._VIDEO_RETRY_JSON, encoding="utf-8") as f:
        data = json.load(f)
    entries = list(data.values())
    check("re-queued entry keeps the status id",
          len(entries) == 1 and entries[0].get("status_msg_id") == 555)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 555]
    check("queued notice edits the tracked status (no stacking)",
          len(edits) == 1 and "queued" in edits[0][3])


def t_fallback_honest_failure_edits_status():
    print("-- timeout fallback: honest failure edits the status --")
    _fresh_stores()
    monkey = []
    _stub_downloads(monkey, success=False)
    monkey.append(("yds", "mp3_block_wave_active", lambda: False))
    monkey.append(("yds", "download_hit_block_wave", lambda: False))
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        _deliver_video_local(bot, 9, 7, "https://youtu.be/abc",
                             status_msg_id=555)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 555]
    fresh = [c for c in bot.calls if c[0] == "send_message"]
    check("honest failure edits the tracked status",
          len(edits) == 1 and "genuine failure" in edits[0][3])
    check("no stacked fresh message", len(fresh) == 0)


# ------------------------------------------------------------- retry tick

def _seed_queue(entries):
    with open(yds._VIDEO_RETRY_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f)


def _tick_stubs(monkey, success=True, wave=False):
    _stub_downloads(monkey, success=success)
    monkey.append(("yds", "_yt_breaker_open", lambda: False))
    monkey.append(("yds", "mp3_block_wave_active", lambda: wave))


def t_tick_autodelivery_deletes_status():
    print("-- retry tick: auto-delivery deletes the queued notice --")
    _fresh_stores()
    _seed_queue({"k1": {"chat_id": 9, "user_id": 7, "url": "https://youtu.be/a",
                        "video_id": "a", "ts": time.time(), "attempts": 0,
                        "status_msg_id": 501, "key": "k1"}})
    monkey = []
    _tick_stubs(monkey, success=True, wave=False)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        video_retry_tick(bot)
    finally:
        _restore(applied)
    check("video auto-delivered", "send_video" in _call_types(bot))
    check("queued notice deleted", ("delete", 9, 501) in bot.calls)
    with open(yds._VIDEO_RETRY_JSON, encoding="utf-8") as f:
        check("entry removed after delivery", json.load(f) == {})


def t_tick_honest_failure_edits_status():
    print("-- retry tick: honest failure edits the queued notice --")
    _fresh_stores()
    _seed_queue({"k1": {"chat_id": 9, "user_id": 7, "url": "https://youtu.be/a",
                        "video_id": "a", "ts": time.time(), "attempts": 0,
                        "status_msg_id": 501, "key": "k1"}})
    monkey = []
    _tick_stubs(monkey, success=False, wave=False)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        video_retry_tick(bot)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 501]
    fresh = [c for c in bot.calls
             if c[0] == "send_message" and c[1] == 9]
    check("queued notice edited into honest failure",
          len(edits) == 1 and "genuine failure" in edits[0][3])
    check("no stacked fresh message", len(fresh) == 0)


def t_tick_exhausted_edits_status():
    print("-- retry tick: gave-up notice edits the queued notice --")
    _fresh_stores()
    _seed_queue({"k1": {"chat_id": 9, "user_id": 7, "url": "https://youtu.be/a",
                        "video_id": "a", "ts": time.time(), "attempts": 3,
                        "status_msg_id": 501, "key": "k1"}})
    monkey = []
    _tick_stubs(monkey, success=False, wave=False)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        video_retry_tick(bot)
    finally:
        _restore(applied)
    edits = [c for c in bot.calls if c[0] == "edit" and c[2] == 501]
    check("queued notice edited into gave-up notice",
          len(edits) == 1 and "tried 3 times" in edits[0][3])


def t_tick_no_status_id_sends_fresh():
    print("-- retry tick: legacy entry without id still notifies --")
    _fresh_stores()
    _seed_queue({"k1": {"chat_id": 9, "user_id": 7, "url": "https://youtu.be/a",
                        "video_id": "a", "ts": time.time(), "attempts": 0,
                        "key": "k1"}})
    monkey = []
    _tick_stubs(monkey, success=False, wave=False)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        video_retry_tick(bot)  # must not raise
    finally:
        _restore(applied)
    fresh = [c for c in bot.calls
             if c[0] == "send_message" and "genuine failure" in c[2]]
    check("falls back to a fresh message", len(fresh) == 1)


def t_tick_autodelivery_no_status_id_ok():
    print("-- retry tick: auto-delivery without id never raises --")
    _fresh_stores()
    _seed_queue({"k1": {"chat_id": 9, "user_id": 7, "url": "https://youtu.be/a",
                        "video_id": "a", "ts": time.time(), "attempts": 0,
                        "key": "k1"}})
    monkey = []
    _tick_stubs(monkey, success=True, wave=False)
    applied = _apply(monkey)
    bot = FakeBot()
    try:
        video_retry_tick(bot)  # must not raise
    finally:
        _restore(applied)
    check("video auto-delivered", "send_video" in _call_types(bot))


TESTS = [
    t_local_success_deletes_status,
    t_local_success_delete_failure_ok,
    t_local_send_failure_keeps_honest_notice,
    t_invalid_url_keeps_honest_notice,
    t_wave_queue_edits_status_and_tracks_id,
    t_handoff_passes_status_id,
    t_worker_done_video_deletes_status,
    t_worker_done_video_delete_failure_ok,
    t_fallback_success_deletes_status,
    t_fallback_wave_carries_status_id,
    t_fallback_honest_failure_edits_status,
    t_tick_autodelivery_deletes_status,
    t_tick_honest_failure_edits_status,
    t_tick_exhausted_edits_status,
    t_tick_no_status_id_sends_fresh,
    t_tick_autodelivery_no_status_id_ok,
]

if __name__ == "__main__":
    for t in TESTS:
        try:
            t()
        except Exception as e:
            FAIL += 1
            FAILURES.append(f"{t.__name__} raised {e!r}")
            print(f"  FAIL {t.__name__} raised {e!r}")
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failures:", FAILURES)
    sys.exit(1 if FAIL else 0)
