"""Round-38 tests: the retry queues never go silent.

The bug: a queued MP3/video that burned all 3 attempts during a block
wave was filtered out of *_retry_due() forever — no notice, no removal,
user promised automatic delivery got silence. The permanent fix: the
tick sweeps exhausted entries with ONE honest final notice each, and
failed video downloads tidy their .part partials instead of leaking them.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
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


def _fresh_retry_stores():
    tmp = tempfile.mkdtemp()
    yds._MP3_RETRY_JSON = os.path.join(tmp, "mp3_retry_queue.json")
    yds._VIDEO_RETRY_JSON = os.path.join(tmp, "video_retry_queue.json")
    return tmp


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id=None, text=None, **kw):
        self.sent.append((chat_id, text))

    def send_audio(self, chat_id=None, audio=None, **kw):
        self.sent.append((chat_id, "audio"))


def t_mp3_retry_exhausted_filters():
    print("-- mp3_retry_exhausted: only burned-out, non-expired entries --")
    _fresh_retry_stores()
    now = time.time()
    _write(yds._MP3_RETRY_JSON, {
        "dead": {"chat_id": 1, "artist": "A", "song": "S",
                 "ts": now - 100, "attempts": 3},
        "live": {"chat_id": 1, "artist": "A", "song": "T",
                 "ts": now - 100, "attempts": 2},
        "old": {"chat_id": 1, "artist": "A", "song": "O",
                "ts": now - 4 * 3600, "attempts": 3},
    })
    out = yds.mp3_retry_exhausted()
    keys = [e["key"] for e in out]
    check("exhausted entry found", keys == ["dead"])
    check("live entry not swept", "live" not in keys)
    check("TTL-expired entry left for silent prune", "old" not in keys)


def t_mp3_retry_exhausted_missing_file():
    print("-- mp3_retry_exhausted: missing file never raises --")
    _fresh_retry_stores()
    check("returns []", yds.mp3_retry_exhausted() == [])


def t_video_retry_exhausted_filters():
    print("-- video_retry_exhausted: mirrors the MP3 queue --")
    _fresh_retry_stores()
    now = time.time()
    _write(yds._VIDEO_RETRY_JSON, {
        "dead": {"chat_id": 1, "url": "https://youtu.be/x", "video_id": "x",
                 "ts": now - 100, "attempts": 3},
        "live": {"chat_id": 1, "url": "https://youtu.be/y", "video_id": "y",
                 "ts": now - 100, "attempts": 1},
    })
    out = yds.video_retry_exhausted()
    check("only the burned-out entry",
          [e["key"] for e in out] == ["dead"])


def t_mp3_tick_notifies_and_removes_exhausted():
    print("-- mp3_retry_tick: exhausted entry → honest notice + removed --")
    _fresh_retry_stores()
    now = time.time()
    _write(yds._MP3_RETRY_JSON, {
        "k1": {"chat_id": 42, "user_id": 42, "artist": "Billie Eilish",
               "song": "WILDFLOWER", "ts": now - 100, "attempts": 3},
    })
    bot = FakeBot()
    handlers.mp3_retry_tick(bot)
    remaining = _read(yds._MP3_RETRY_JSON)
    check("entry removed after notice", remaining == {})
    check("exactly one notice sent", len(bot.sent) == 1)
    chat_id, text = bot.sent[0]
    check("notice goes to the right chat", chat_id == 42)
    check("notice names the song",
          "Billie Eilish" in text and "WILDFLOWER" in text)
    check("notice is honest about giving up",
          "3 times" in text and "Tap MP3 again" in text)


def t_mp3_tick_exhausted_sweep_runs_during_wave():
    print("-- mp3_retry_tick: sweep runs even with breaker open --")
    _fresh_retry_stores()
    now = time.time()
    _write(yds._MP3_RETRY_JSON, {
        "k1": {"chat_id": 7, "user_id": 7, "artist": "A",
               "song": "S", "ts": now - 100, "attempts": 5},
    })
    orig = yds._yt_breaker_open
    yds._yt_breaker_open = lambda: True  # wave active: due=[] guaranteed
    try:
        bot = FakeBot()
        handlers.mp3_retry_tick(bot)
    finally:
        yds._yt_breaker_open = orig
    check("notice still sent mid-wave", len(bot.sent) == 1)
    check("entry removed mid-wave", _read(yds._MP3_RETRY_JSON) == {})


def t_video_tick_notifies_and_removes_exhausted():
    print("-- video_retry_tick: exhausted entry → honest notice + removed --")
    _fresh_retry_stores()
    now = time.time()
    _write(yds._VIDEO_RETRY_JSON, {
        "k1": {"chat_id": 42, "user_id": 42,
               "url": "https://www.youtube.com/watch?v=abc",
               "video_id": "abc", "ts": now - 100, "attempts": 3},
    })
    bot = FakeBot()
    handlers.video_retry_tick(bot)
    check("entry removed after notice", _read(yds._VIDEO_RETRY_JSON) == {})
    check("exactly one notice sent", len(bot.sent) == 1)
    chat_id, text = bot.sent[0]
    check("notice goes to the right chat", chat_id == 42)
    check("notice invites a fresh retry",
          "3 times" in text and "Send the link again" in text)


def t_tidy_part_files():
    print("-- _tidy_part_files: partials removed, real files kept --")
    d = tempfile.mkdtemp()
    old = os.getcwd()
    os.chdir(d)
    try:
        open("youtube_abc123.mp4.part", "w").write("x")
        open("youtube_abc123.f248.webm.part", "w").write("x")
        open("youtube_abc123.mp4", "w").write("x")  # finished file: keep
        open("youtube_other.mp4.part", "w").write("x")  # other id: keep
        yds._tidy_part_files("abc123")
        left = sorted(os.listdir(d))
        check("partials for the id removed",
              left == ["youtube_abc123.mp4", "youtube_other.mp4.part"])
        check("never raises on missing id", yds._tidy_part_files("nope") is None)
    finally:
        os.chdir(old)


TESTS = [
    t_mp3_retry_exhausted_filters,
    t_mp3_retry_exhausted_missing_file,
    t_video_retry_exhausted_filters,
    t_mp3_tick_notifies_and_removes_exhausted,
    t_mp3_tick_exhausted_sweep_runs_during_wave,
    t_video_tick_notifies_and_removes_exhausted,
    t_tidy_part_files,
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
