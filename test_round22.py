"""Round-22 tests: card-noise trim, no-lyrics photo fix, /download wave self-registration.

1. The no-lyrics card sentence is one short line now ("No lyrics — instrumental
   track"), not the three-clause lecture.
2. _CallbackFakeMessage proxies reply_photo — a button tap can open the photo
   card (this is exactly what crashed in production: 'FakeMessage' object has
   no attribute 'reply_photo').
3. /download registers a YouTube block wave itself: a hard block error
   ("Sign in to confirm you're not a bot") trips the shared breaker, so
   download_command queues the request (no ❌) and the retry tick can deliver
   it later. Genuine failures (private video, bad URL, …) do NOT trip the
   breaker and do NOT queue.
4. No ❌ anywhere in the /download failure outputs (user hates it) — 😕 instead.
"""
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from handlers import _no_lyrics_card_text, _CallbackFakeMessage
import services.youtube_downloader_service as yds

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


# ── 1. Short card sentence ────────────────────────────────────────────────
t = _no_lyrics_card_text('Chloe Flower', 'Song for Snow', 'Classical Crossover',
                         'She Composed: The Holidays', 'focus')
check("card: short no-lyrics line",
      "No lyrics \u2014 instrumental track" in t, repr(t))
check("card: old lecture gone",
      "typical for instrumentals" not in t and "Let the music do the talking" not in t)
check("card: still has album/genre/mood",
      "She Composed: The Holidays" in t and "Classical Crossover" in t
      and "Focus Mix" in t)

# ── 2. FakeMessage proxies reply_photo ────────────────────────────────────
real = MagicMock()
real.message_id = 99
real.chat = MagicMock()
fm = _CallbackFakeMessage(real, real.chat)
for meth in ("reply_text", "reply_video", "reply_audio", "reply_photo"):
    check(f"fake message proxies {meth}", hasattr(fm, meth) and callable(getattr(fm, meth)))
fm.reply_photo("photo-bytes", caption="cap")
check("reply_photo delegates to real message",
      real.reply_photo.call_args is not None
      and real.reply_photo.call_args[0][0] == "photo-bytes")

# ── 3. /download wave self-registration ───────────────────────────────────
yds._YT_BLOCKED_UNTIL = 0.0  # breaker closed


class FakeYDL:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        import yt_dlp
        raise yt_dlp.utils.DownloadError(
            "ERROR: [youtube] abc123: Sign in to confirm you\u2019re not a bot.")


with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDL):
    ok, msg = yds.download_youtube_video("https://youtu.be/abc123")

check("wave failure: returns False", ok is False)
check("wave failure: breaker tripped by the download itself",
      yds.mp3_block_wave_active())
check("wave failure: no \u274c in message", "\u274c" not in msg, repr(msg[:60]))
check("wave failure: explains the block",
      "blocking" in msg.lower() or "bot check" in msg.lower(), repr(msg[:120]))

# genuine failure must NOT trip the breaker
yds._YT_BLOCKED_UNTIL = 0.0


class FakeYDLPrivate(FakeYDL):
    def extract_info(self, url, download=False):
        import yt_dlp
        raise yt_dlp.utils.DownloadError(
            "ERROR: [youtube] abc123: Private video. Sign in if you have access.")


with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDLPrivate):
    ok2, msg2 = yds.download_youtube_video("https://youtu.be/abc123")

check("private video: returns False", ok2 is False)
check("private video: breaker NOT tripped", not yds.mp3_block_wave_active())
check("private video: no \u274c in message", "\u274c" not in msg2)
check("private video: honest reason", "private" in msg2.lower())

# invalid URL: no trip, no ❌
yds._YT_BLOCKED_UNTIL = 0.0
ok3, msg3 = yds.download_youtube_video("https://example.com/nope")
check("bad url: returns False", ok3 is False)
check("bad url: breaker NOT tripped", not yds.mp3_block_wave_active())
check("bad url: no \u274c in message", "\u274c" not in msg3)

# ── 4. download_command queues on a self-tripped wave ─────────────────────
# Simulate: real download_youtube_video hits the wave (breaker trips inside),
# then download_command must show the queued notice, not a failure.
yds._YT_BLOCKED_UNTIL = 0.0


class FakeProcessing:
    def __init__(self):
        self.text = ""

    def edit_text(self, t, **kw):
        self.text = t


class FakeMsg:
    def __init__(self, processing):
        self._p = processing

    def reply_text(self, t, **kw):
        return self._p


class FakeUpdate:
    def __init__(self, processing):
        self.effective_user = MagicMock()
        self.effective_user.id = 777
        self.effective_chat = MagicMock()
        self.effective_chat.id = 888
        self.message = FakeMsg(processing)


class FakeContext:
    args = ["https://youtu.be/abc123"]


processing = FakeProcessing()
with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDL):
    handlers.download_command(FakeUpdate(processing), FakeContext())

check("command: wave failure shows queued notice, not failure",
      "queued" in processing.text.lower() and "\u274c" not in processing.text,
      repr(processing.text[:100]))
check("command: no re-tap needed line",
      "No need to tap again" in processing.text, repr(processing.text[:200]))
check("command: entry actually queued for retry",
      any("abc123" in str(v.get("url", "")) for v in
          __import__("json").load(open(yds._VIDEO_RETRY_JSON)).values())
      if os.path.exists(yds._VIDEO_RETRY_JSON) else False)

# cleanup: don't leave the test queue entry or an open breaker behind
try:
    if os.path.exists(yds._VIDEO_RETRY_JSON):
        data = __import__("json").load(open(yds._VIDEO_RETRY_JSON))
        for k in [k for k, v in data.items()
                  if v.get("user_id") == 777]:
            data.pop(k, None)
        __import__("json").dump(data, open(yds._VIDEO_RETRY_JSON, "w"))
except Exception:
    pass
yds._YT_BLOCKED_UNTIL = 0.0
time.sleep(0)  # no-op, keeps linters calm about the import

print(f"\nround22: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
