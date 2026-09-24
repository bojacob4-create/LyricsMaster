"""Round-23 tests: only wave-caused /download failures queue for auto-retry.

Reported bug (2026-09-24, user's Telegram test): during an open YouTube block
wave, `/download jnhgfghh` (garbage) got the "queued — I'll retry
automatically" treatment instead of the honest invalid-URL notice. The queue
gate asked "is a wave window open?" instead of "did THIS download fail
because of the wave?", so any genuine failure landing mid-wave walked
through the open door and got queued.

Fix: download_youtube_video() records a per-call verdict
(download_hit_block_wave()); download_command queues only when that verdict
is True. Genuine failures mid-wave get the honest notice immediately and are
never queued.
"""
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
import services.youtube_downloader_service as yds

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _read_queue():
    try:
        with open(yds._VIDEO_RETRY_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _queue_urls():
    return [str(v.get("url", "")) for v in _read_queue().values()
            if v.get("user_id") == 4242]


def _clean_test_entries():
    try:
        data = _read_queue()
        for k in [k for k, v in data.items() if v.get("user_id") == 4242]:
            data.pop(k, None)
        with open(yds._VIDEO_RETRY_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


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
        self.effective_user.id = 4242
        self.effective_chat = MagicMock()
        self.effective_chat.id = 4343
        self.message = FakeMsg(processing)


class FakeContext:
    def __init__(self, arg):
        self.args = [arg]


def run_command(arg):
    processing = FakeProcessing()
    handlers.download_command(FakeUpdate(processing), FakeContext(arg))
    return processing.text


def open_wave():
    """Simulate an active block wave without network."""
    yds._YT_BLOCKED_UNTIL = time.time() + 900


def close_wave():
    yds._YT_BLOCKED_UNTIL = 0.0


class FakeYDLWave:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        import yt_dlp
        raise yt_dlp.utils.DownloadError(
            "ERROR: [youtube] abc123: Sign in to confirm you're not a bot.")


class FakeYDLPrivate(FakeYDLWave):
    def extract_info(self, url, download=False):
        import yt_dlp
        raise yt_dlp.utils.DownloadError(
            "ERROR: [youtube] abc123: Private video.")


# ── 1. The reported bug: garbage URL mid-wave ─────────────────────────────
_clean_test_entries()
open_wave()
text = run_command("jnhgfghh")
check("mid-wave garbage: honest invalid-URL notice",
      "Invalid YouTube URL" in text, repr(text[:80]))
check("mid-wave garbage: no queued promise",
      "queued" not in text.lower(), repr(text[:120]))
check("mid-wave garbage: NOT added to retry queue",
      not any("jnhgfghh" in u for u in _queue_urls()),
      repr(_queue_urls()))
check("mid-wave garbage: verdict flag is False",
      yds.download_hit_block_wave() is False)

# ── 2. Private video mid-wave: honest notice, no queue ────────────────────
_clean_test_entries()
open_wave()
with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDLPrivate):
    text2 = run_command("https://youtu.be/abc123")
check("mid-wave private: honest notice",
      "private" in text2.lower(), repr(text2[:80]))
check("mid-wave private: not queued",
      "queued" not in text2.lower()
      and not any("abc123" in u for u in _queue_urls()))
check("mid-wave private: verdict flag is False",
      yds.download_hit_block_wave() is False)

# ── 3. Genuine wave failure still queues (round-22 behavior kept) ─────────
_clean_test_entries()
close_wave()
with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDLWave):
    text3 = run_command("https://youtu.be/abc123")
check("wave failure: verdict flag is True",
      yds.download_hit_block_wave() is True)
check("wave failure: queued notice shown",
      "queued" in text3.lower(), repr(text3[:80]))
check("wave failure: entry queued",
      any("abc123" in u for u in _queue_urls()),
      repr(_queue_urls()))

# ── 4. Flag resets between calls ──────────────────────────────────────────
close_wave()
with patch.object(yds.yt_dlp, "YoutubeDL", FakeYDLWave):
    yds.download_youtube_video("https://youtu.be/abc123")
check("flag True after wave", yds.download_hit_block_wave() is True)
yds.download_youtube_video("jnhgfghh")
check("flag False after genuine failure", yds.download_hit_block_wave() is False)
ok, _msg = yds.download_youtube_video("jnhgfghh")
check("genuine failure returns False", ok is False)

_clean_test_entries()
close_wave()

print(f"\nround23: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
