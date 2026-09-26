"""Round-75 tests: self-cleaning MP3 status messages.

One tap → one short "On it" status message that never outlives its job:
- success → status deleted before the audio lands
- block wave → status edited into the queued notice (no stacked second
  message); the queue entry remembers the id so the retry tick deletes it
  on auto-delivery
- honest failure → status edited into the failure notice
- worker DONE → status deleted after the copy
- helpers never raise; delete/edit failures degrade gracefully
"""
import json
import os
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from handlers import (
    _mp3_status_delete,
    _mp3_status_update,
    _MP3_QUEUED_TEXT,
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
    return tmp


class FakeBot:
    """Records bot API calls. fail_delete/fail_edit simulate a gone message."""

    def __init__(self, fail_delete=False, fail_edit=False, fail_audio=False):
        self.calls = []
        self.fail_delete = fail_delete
        self.fail_edit = fail_edit
        self.fail_audio = fail_audio
        self._next_id = 1000
        self._audio_calls = 0

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

    def send_audio(self, chat_id, audio, caption=None, **kw):
        self._audio_calls += 1
        if self.fail_audio and self._audio_calls == 1:
            raise RuntimeError("stale file_id")
        self.calls.append(("send_audio", chat_id, caption))
        return types.SimpleNamespace(
            audio=types.SimpleNamespace(file_id="fid1"))

    def copy_message(self, chat_id, from_chat_id, message_id, caption=None,
                     **kw):
        self.calls.append(("copy_message", chat_id, caption))
        return types.SimpleNamespace(
            audio=types.SimpleNamespace(file_id="fid9"))


def _call_types(bot):
    return [c[0] for c in bot.calls]


# ---------------------------------------------------------------- helpers

def t_status_delete_none_is_noop():
    print("-- _mp3_status_delete: None id → no call, never raises --")
    bot = FakeBot()
    _mp3_status_delete(bot, 9, None)
    _mp3_status_delete(bot, 9, 0)
    check("no calls for empty id", bot.calls == [])


def t_status_update_none_sends_fresh():
    print("-- _mp3_status_update: no id → sends fresh message --")
    bot = FakeBot()
    new_id = _mp3_status_update(bot, 9, None, "hello")
    check("send_message used", "send_message" in _call_types(bot))
    check("returns new id", isinstance(new_id, int) and new_id > 0)


def t_status_update_edits_in_place():
    print("-- _mp3_status_update: existing id → edit, same id back --")
    bot = FakeBot()
    new_id = _mp3_status_update(bot, 9, 555, "queued notice")
    check("edit used, no send_message",
          ("edit", 9, 555, "queued notice") in bot.calls
          and "send_message" not in _call_types(bot))
    check("same id returned", new_id == 555)


def t_status_update_edit_fallback():
    print("-- _mp3_status_update: edit fails → fresh message, never raises --")
    bot = FakeBot(fail_edit=True)
    new_id = _mp3_status_update(bot, 9, 555, "hello")
    check("fell back to send_message", "send_message" in _call_types(bot))
    check("returned a new id", isinstance(new_id, int) and new_id != 555)


def t_status_delete_failure_is_silent():
    print("-- _mp3_status_delete: Telegram error never raises --")
    bot = FakeBot(fail_delete=True)
    try:
        _mp3_status_delete(bot, 9, 555)
        check("no raise", True)
    except Exception:
        check("no raise", False)


# ---------------------------------------------------------------- command

def t_command_sends_short_status():
    print("-- mp3_command: short status text, id threaded to job --")
    bot = FakeBot()
    captured = {}
    done = threading.Event()

    def fake_bg(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        done.set()

    class FakeMessage:
        def reply_text(self, text, **kw):
            bot.calls.append(("reply_text", text))
            return types.SimpleNamespace(message_id=42)

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=7),
        effective_chat=types.SimpleNamespace(id=9),
        message=FakeMessage())
    context = types.SimpleNamespace(
        args=["Hans", "Zimmer", "-", "Time"], bot=bot)

    orig = handlers._mp3_background_job
    handlers._mp3_background_job = fake_bg
    try:
        handlers.mp3_command(update, context)
        check("background job started", done.wait(5))
    finally:
        handlers._mp3_background_job = orig
        handlers._mp3_in_progress.discard((7, "hans zimmer", "time"))

    texts = [c[1] for c in bot.calls if c[0] == "reply_text"]
    check("exactly one status message", len(texts) == 1)
    short = texts[0] if texts else ""
    check("short one-liner", short == "🎧 On it — Hans Zimmer - Time…")
    check("no lecture paragraph", "feel free to keep using" not in short)
    check("no divider bar", "━━" not in short)
    args = captured.get("args", ())
    check("status_msg_id threaded (positional)",
          len(args) == 8 and args[7] == 42)


# ---------------------------------------------------------------- delivery

def t_success_file_id_deletes_status():
    print("-- _deliver_mp3_result: instant cache → status deleted, audio sent --")
    bot = FakeBot()
    handlers._deliver_mp3_result(
        bot, 9, 7, "A", "S", "A - S", True,
        ("file_id", "fid1", "Title", "Up"), status_msg_id=555)
    types_ = _call_types(bot)
    check("delete called with status id", ("delete", 9, 555) in bot.calls)
    check("audio sent", "send_audio" in types_)
    check("delete before audio",
          types_.index("delete") < types_.index("send_audio"))
    check("no extra status message", "send_message" not in types_)


def t_fresh_download_deletes_status():
    print("-- _deliver_fresh_mp3: status deleted before audio lands --")
    bot = FakeBot()
    orig_note = handlers.note_mp3_file_id
    handlers.note_mp3_file_id = lambda *a: None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3",
                                         delete=False) as f:
            f.write(b"fake-audio")
            path = f.name
        handlers._deliver_fresh_mp3(
            bot, 9, "A", "S", (path, None, "Title", "Up"),
            status_msg_id=555)
    finally:
        handlers.note_mp3_file_id = orig_note
    types_ = _call_types(bot)
    check("delete called with status id", ("delete", 9, 555) in bot.calls)
    check("audio sent", "send_audio" in types_)
    check("delete before audio",
          types_.index("delete") < types_.index("send_audio"))


def t_delete_failure_never_breaks_delivery():
    print("-- success path: delete raising → audio still delivered --")
    bot = FakeBot(fail_delete=True)
    try:
        handlers._deliver_mp3_result(
            bot, 9, 7, "A", "S", "A - S", True,
            ("file_id", "fid1", "Title", "Up"), status_msg_id=555)
        check("audio still sent", "send_audio" in _call_types(bot))
    except Exception as e:
        check(f"no raise ({e})", False)


def t_queue_edits_status_and_remembers_id():
    print("-- block wave: status edited into queued notice, id in queue --")
    _fresh_stores()
    bot = FakeBot()
    orig_wave = yds.mp3_block_wave_active
    yds.mp3_block_wave_active = lambda: True
    try:
        handlers._deliver_mp3_result(
            bot, 9, 7, "A", "S", "A - S", False, "honest fail text",
            status_msg_id=555)
    finally:
        yds.mp3_block_wave_active = orig_wave
    check("status edited (not a new message)",
          ("edit", 9, 555, _MP3_QUEUED_TEXT) in bot.calls)
    check("no stacked queued message",
          not any(c[0] == "send_message" and "blocking downloads" in c[2]
                  for c in bot.calls))
    with open(yds._MP3_RETRY_JSON, encoding="utf-8") as f:
        data = json.load(f)
    entries = list(data.values())
    check("one queue entry", len(entries) == 1)
    check("queue entry remembers status id",
          entries and entries[0].get("status_msg_id") == 555)


def t_failure_edits_status():
    print("-- honest failure: status edited into the failure notice --")
    bot = FakeBot()
    orig_wave = yds.mp3_block_wave_active
    yds.mp3_block_wave_active = lambda: False
    try:
        handlers._deliver_mp3_result(
            bot, 9, 7, "A", "S", "A - S", False, "😞 honest fail",
            status_msg_id=555)
    finally:
        yds.mp3_block_wave_active = orig_wave
    check("status edited into failure text",
          ("edit", 9, 555, "😞 honest fail") in bot.calls)
    check("no separate failure message",
          "send_message" not in _call_types(bot))


def t_stale_file_id_replaces_status():
    print("-- stale cache: fresh-fetch message becomes the status --")
    bot = FakeBot(fail_audio=True)
    orig_dl = handlers.download_audio_for_song
    orig_forget = handlers.forget_mp3_file_id
    orig_note = handlers.note_mp3_file_id
    handlers.forget_mp3_file_id = lambda *a: None
    handlers.note_mp3_file_id = lambda *a: None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3",
                                         delete=False) as f:
            f.write(b"fake-audio")
            path = f.name
        handlers.download_audio_for_song = lambda a, s: (
            True, (path, None, "Title", "Up"))
        handlers._deliver_mp3_result(
            bot, 9, 7, "A", "S", "A - S", True,
            ("file_id", "stale", "Title", "Up"), status_msg_id=555)
    finally:
        handlers.download_audio_for_song = orig_dl
        handlers.forget_mp3_file_id = orig_forget
        handlers.note_mp3_file_id = orig_note
    check("original status deleted", ("delete", 9, 555) in bot.calls)
    fresh = [c for c in bot.calls
             if c[0] == "send_message" and "Cached copy expired" in c[2]]
    check("fresh-fetch notice sent", len(fresh) == 1)
    check("audio eventually sent", "send_audio" in _call_types(bot))


# ---------------------------------------------------------------- worker path

def t_post_job_carries_status_id():
    print("-- post_job: status_msg_id stored in the job entry --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-1001", TELEGRAM_TOKEN="main")
    orig = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    try:
        jid = svc.post_job(42, 7, "url", kind="audio", status_msg_id=777)
        entry = svc.get_job_entry(jid)
        check("entry carries status id",
              entry is not None and entry.get("status_msg_id") == 777)
        jid2 = svc.post_job(42, 7, "url", kind="audio")
        entry2 = svc.get_job_entry(jid2)
        check("default is 0 (video path untouched)",
              entry2 is not None and entry2.get("status_msg_id") == 0)
    finally:
        svc._api_send_message = orig
        restore()


def t_worker_done_deletes_status():
    print("-- worker DONE (audio): status deleted after copy --")
    _fresh_stores()
    restore = _with_env(WORKER_CHANNEL_ID="-10099", TELEGRAM_TOKEN="main")
    orig_send = svc._api_send_message
    svc._api_send_message = lambda token, chat_id, text: True
    bot = FakeBot()
    try:
        jid = svc.post_job(42, 7, "url", title="A - S", kind="audio",
                           artist="A", song="S", status_msg_id=777)
        update = types.SimpleNamespace(
            channel_post=types.SimpleNamespace(
                text=f"DONE {jid} 12345",
                chat=types.SimpleNamespace(id=-10099)))
        context = types.SimpleNamespace(bot=bot)
        handlers.worker_channel_post(update, context)
    finally:
        svc._api_send_message = orig_send
        restore()
    check("copy delivered", "copy_message" in _call_types(bot))
    check("status deleted", ("delete", 42, 777) in bot.calls)


# ---------------------------------------------------------------- retry tick

def _enqueue_with_status(status_id):
    with open(yds._MP3_RETRY_JSON, "w", encoding="utf-8") as f:
        json.dump({"k1": {"chat_id": 9, "user_id": 7, "artist": "A",
                          "song": "S", "status_msg_id": status_id,
                          "ts": time.time(), "attempts": 0,
                          "key": "k1"}}, f)


def t_retry_tick_autodelivery_deletes_status():
    print("-- mp3_retry_tick: auto-delivery deletes the queued status --")
    _fresh_stores()
    _enqueue_with_status(555)
    bot = FakeBot()
    orig_breaker = yds._yt_breaker_open
    orig_dl = handlers.download_audio_for_song
    yds._yt_breaker_open = lambda: False
    handlers.download_audio_for_song = lambda a, s: (
        True, ("file_id", "fid1", "T", "U"))
    try:
        handlers.mp3_retry_tick(bot)
    finally:
        yds._yt_breaker_open = orig_breaker
        handlers.download_audio_for_song = orig_dl
    check("status deleted", ("delete", 9, 555) in bot.calls)
    check("audio delivered", "send_audio" in _call_types(bot))
    with open(yds._MP3_RETRY_JSON, encoding="utf-8") as f:
        check("queue entry removed", json.load(f) == {})


def t_retry_tick_final_failure_edits_status():
    print("-- mp3_retry_tick: final failure edits the queued status --")
    _fresh_stores()
    _enqueue_with_status(555)
    bot = FakeBot()
    orig_breaker = yds._yt_breaker_open
    orig_wave = yds.mp3_block_wave_active
    orig_dl = handlers.download_audio_for_song
    yds._yt_breaker_open = lambda: False
    yds.mp3_block_wave_active = lambda: False
    handlers.download_audio_for_song = lambda a, s: (False, "😞 final fail")
    try:
        handlers.mp3_retry_tick(bot)
    finally:
        yds._yt_breaker_open = orig_breaker
        yds.mp3_block_wave_active = orig_wave
        handlers.download_audio_for_song = orig_dl
    check("status edited into final notice",
          ("edit", 9, 555, "😞 final fail") in bot.calls)
    check("no separate notice", "send_message" not in _call_types(bot))


TESTS = [
    t_status_delete_none_is_noop,
    t_status_update_none_sends_fresh,
    t_status_update_edits_in_place,
    t_status_update_edit_fallback,
    t_status_delete_failure_is_silent,
    t_command_sends_short_status,
    t_success_file_id_deletes_status,
    t_fresh_download_deletes_status,
    t_delete_failure_never_breaks_delivery,
    t_queue_edits_status_and_remembers_id,
    t_failure_edits_status,
    t_stale_file_id_replaces_status,
    t_post_job_carries_status_id,
    t_worker_done_deletes_status,
    t_retry_tick_autodelivery_deletes_status,
    t_retry_tick_final_failure_edits_status,
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
