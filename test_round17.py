"""Round-17 tests: /download retry queue (no-re-tap for video block waves).

Mirrors the MP3 queue design: a /download that fails during a YouTube
block wave is queued, retried every 5 min once the wave clears, and the
video is auto-delivered. Genuine failures (unavailable/too large/bad URL)
still get the honest notice immediately and are never queued.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from services import youtube_downloader_service as yds

passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok    {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {detail}")

# ── isolated queue file + breaker control ────────────────────────────────
tmp = tempfile.mkdtemp()
queue_path = os.path.join(tmp, "video_retry_queue.json")
orig_queue = yds._VIDEO_RETRY_JSON
orig_blocked = yds._YT_BLOCKED_UNTIL
yds._VIDEO_RETRY_JSON = queue_path

def breaker_closed():
    yds._YT_BLOCKED_UNTIL = 0

def breaker_open():
    yds._YT_BLOCKED_UNTIL = time.time() + 900

def read_queue():
    try:
        with open(queue_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

try:
    URL = "https://youtu.be/1WwS3IcEzcA?si=x"
    breaker_closed()

    # 1. enqueue works and stores what the tick needs
    check("enqueue returns True", yds.video_retry_enqueue(111, 222, URL) is True)
    q = read_queue()
    check("enqueue stores one entry", len(q) == 1, repr(q))
    e = next(iter(q.values()))
    check("entry has chat_id/url/video_id/ts/attempts",
          all(k in e for k in ("chat_id", "url", "video_id", "ts", "attempts"))
          and e["chat_id"] == 111 and e["url"] == URL
          and e["video_id"] == "1WwS3IcEzcA" and e["attempts"] == 0,
          repr(e))

    # 2. due when breaker closed
    due = yds.video_retry_due()
    check("due returns entry when wave cleared",
          len(due) == 1 and due[0]["key"] == "222:1WwS3IcEzcA", repr(due))

    # 3. not due when breaker open
    breaker_open()
    check("due empty while wave active", yds.video_retry_due() == [])
    breaker_closed()

    # 4. re-enqueue same video+user refreshes instead of duplicating
    yds.video_retry_enqueue(111, 222, URL)
    check("re-enqueue does not duplicate", len(read_queue()) == 1)

    # 5. different user, same video → separate entry
    yds.video_retry_enqueue(333, 444, URL)
    check("per-user keys are independent", len(read_queue()) == 2, repr(read_queue()))

    # 6. attempt budget: after max attempts the entry is no longer due
    key = "222:1WwS3IcEzcA"
    for _ in range(yds._RETRY_MAX_ATTEMPTS):
        yds.video_retry_note_attempt(key)
    due_keys = [d["key"] for d in yds.video_retry_due()]
    check("exhausted entry leaves the due set",
          key not in due_keys and "444:1WwS3IcEzcA" in due_keys, repr(due_keys))

    # 7. TTL expiry: old entries are not due
    old = {"chat_id": 111, "user_id": 222, "url": URL,
           "video_id": "oldvid", "ts": time.time() - yds._RETRY_TTL_SECS - 1,
           "attempts": 0}
    q = read_queue(); q["222:oldvid"] = old
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(q, f)
    check("expired entry not due",
          "222:oldvid" not in [d["key"] for d in yds.video_retry_due()])

    # 8. remove drops the entry
    yds.video_retry_remove("444:1WwS3IcEzcA")
    check("remove drops entry",
          "444:1WwS3IcEzcA" not in read_queue())

    # 9. tick delivers the video on success and cleans up
    yds.video_retry_enqueue(111, 222, URL)
    fake_file = os.path.join(tmp, "youtube_1WwS3IcEzcA.mp4")
    with open(fake_file, "wb") as f:
        f.write(b"x" * 64)
    orig_dl = handlers.download_youtube_video
    orig_cleanup = handlers.cleanup_video
    handlers.download_youtube_video = lambda u: (True, (fake_file, "✅ Downloaded!"))
    handlers.cleanup_video = lambda p: os.path.exists(p) and os.remove(p)

    class FakeBot:
        def __init__(self):
            self.videos = []
            self.messages = []
        def send_video(self, chat_id, video, caption=None, supports_streaming=False):
            self.videos.append((chat_id, caption))
        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    fake = FakeBot()
    handlers.video_retry_tick(fake)
    check("tick sends the video to the right chat",
          fake.videos == [(111, "🎉 Here's your video!\n✅ Ready — your queued download")],
          repr(fake.videos))
    check("tick removes delivered entry",
          "222:1WwS3IcEzcA" not in read_queue())
    check("tick cleans up the temp file", not os.path.exists(fake_file))

    # 10. tick on genuine (non-wave) failure: removes entry, sends notice once
    yds.video_retry_enqueue(111, 222, URL)
    handlers.download_youtube_video = lambda u: (False, "❌ This video isn't available.")
    fake2 = FakeBot()
    handlers.video_retry_tick(fake2)
    check("genuine failure removed from queue",
          "222:1WwS3IcEzcA" not in read_queue())
    check("genuine failure notice sent once",
          fake2.messages == [(111, "❌ This video isn't available.")] and not fake2.videos,
          repr(fake2.messages))

    # 11. tick while wave active: nothing attempted, entry stays queued
    yds.video_retry_enqueue(111, 222, URL)
    breaker_open()
    called = []
    handlers.download_youtube_video = lambda u: called.append(u) or (True, ("x", "y"))
    fake3 = FakeBot()
    handlers.video_retry_tick(fake3)
    check("no attempt while wave active",
          called == [] and fake3.videos == [] and "222:1WwS3IcEzcA" in read_queue())
    breaker_closed()

    handlers.download_youtube_video = orig_dl
    handlers.cleanup_video = orig_cleanup

    # 12. download_command source: wave failure → queue path (not bare error)
    import inspect
    src = inspect.getsource(handlers.download_command)
    check("download_command queues on wave",
          "video_retry_enqueue" in src and "[VIDEO][QUEUED]" in src)
    check("download_command queued message promises no re-tap",
          "No need to tap again" in src)

    # 13. bot.py wiring: job registered every 5 min
    bsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")).read()
    check("bot.py schedules video_retry every 5 min",
          "id='video_retry'" in bsrc and "minutes=5" in bsrc)
    check("bot.py imports video_retry_tick", "video_retry_tick" in bsrc)
finally:
    yds._VIDEO_RETRY_JSON = orig_queue
    yds._YT_BLOCKED_UNTIL = orig_blocked

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
