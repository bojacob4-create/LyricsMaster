"""Round-33 tests: /download froze the user for 4+ minutes and never queued.

Production 2026-09-24 ~20:16 +03 (user's Telegram test): after the round-32
code fixes the download REALLY started — the android client pulled 77% of
the ~16MB video, then YouTube killed the TCP connection mid-download with
a NEW mask: "Failed to perform, curl: (56) Connection closed abruptly".
The remaining clients (web/ios/mweb) refused formats; mweb alone burned
~3.5 minutes minting PO tokens during the wave. After ~4.2 minutes the
user got "No compatible format available" — a lie (the video is fine) —
and nothing was queued for auto-retry.

Three gaps:
1. "Connection closed abruptly" / "curl: (56)" was not in the block-error
   hints, so the wave detector missed the new mask.
2. The wave verdict required ALL clients to hit hard block errors. But a
   connection kill MID-DOWNLOAD is wave proof from a single client —
   YouTube only does that when blocking this IP.
3. No wall-clock cap per client: one stuck client (PO-token minting
   spinning, tarpitted extraction) could hold the "Downloading..." spinner
   hostage for minutes with no way out.

Fix:
- The connection-kill family (incl. the new mask) counts as block errors.
- _is_download_stage_kill(): "[download] Got error:" + kill hint from any
  single client -> trip the breaker, mark the wave, ABORT the rotation
  immediately so the caller queues for auto-retry.
- _download_video_with_client_capped(): each client attempt runs in a
  forked child (round-24 pattern) with a hard _VIDEO_CLIENT_TIMEOUT_SECS
  cap — terminate() with SIGKILL escalation on breach.
- A stall-only failure now reports "took too long", not "blocked".
"""
import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp
import services.youtube_downloader_service as yds
from services.youtube_downloader_service import (
    download_youtube_video, download_hit_block_wave,
    _is_block_error_msg, _is_download_stage_kill,
    _download_video_with_client_capped, _yt_breaker_open,
    _YT_CLIENT_ATTEMPTS,
)

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} :: {detail}")


KILL_56 = ("ERROR: \r[download] Got error: Failed to perform, curl: (56) "
           "Connection closed abruptly. See https://curl.se/libcurl/c/"
           "libcurl-errors.html first for more details.. "
           "Giving up after 3 retries")
KILL_REMOTE = ("ERROR: \r[download] Got error: Remote end closed connection "
               "without response. Giving up after 3 retries")
BOT_CHECK = ("ERROR: [youtube] X: Sign in to confirm you're not a bot. "
             "Use --cookies-from-browser or --cookies for the authentication.")
FMT_REFUSAL = ("ERROR: [youtube] X: Requested format is not available. "
               "Use --list-formats for a list of available formats.")
DISK_ERR = "ERROR: [download] Got error: unable to write data to disk."

# ── 1. New mask is a block error ──────────────────────────────────────────
check("curl-56 kill is a block error",
      _is_block_error_msg(KILL_56.lower()))
check("remote-end kill still a block error",
      _is_block_error_msg(KILL_REMOTE.lower()))

# ── 2. Download-stage kill detection ──────────────────────────────────────
check("download-stage curl-56 kill detected",
      _is_download_stage_kill(KILL_56))
check("download-stage remote-end kill detected",
      _is_download_stage_kill(KILL_REMOTE))
check("extraction bot-check is NOT a download-stage kill",
      not _is_download_stage_kill(BOT_CHECK))
check("format refusal is NOT a download-stage kill",
      not _is_download_stage_kill(FMT_REFUSAL))
check("download-stage disk error is NOT a kill",
      not _is_download_stage_kill(DISK_ERR))

# ── 3. Rotation aborts on a single download-stage kill ────────────────────
yds._YT_BLOCKED_UNTIL = 0.0  # breaker closed before the call
attempted = []


def fake_capped_kill(url, video_id, tmpl, client):
    attempted.append(client)
    raise yt_dlp.utils.DownloadError(KILL_56)


with patch.object(yds, '_download_video_with_client_capped', fake_capped_kill):
    ok, result = download_youtube_video(
        "https://www.youtube.com/watch?v=XoiOOiuH8iI")

check("kill aborts rotation after the first client",
      attempted == [_YT_CLIENT_ATTEMPTS[0]], str(attempted))
check("kill returns failure", ok is False)
check("kill trips the shared breaker", _yt_breaker_open())
check("kill marks the wave for auto-queue", download_hit_block_wave() is True)

# ── 4. Timeout: noted, rotation continues, no wave, honest reason ─────────
yds._YT_BLOCKED_UNTIL = 0.0
attempted2 = []


def fake_capped_timeout(url, video_id, tmpl, client):
    attempted2.append(client)
    raise TimeoutError(f"client '{client}' timed out after 150s")


with patch.object(yds, '_download_video_with_client_capped',
                  fake_capped_timeout):
    ok, result = download_youtube_video(
        "https://www.youtube.com/watch?v=XoiOOiuH8iI")

check("timeout tries every client", attempted2 == list(_YT_CLIENT_ATTEMPTS),
      str(attempted2))
check("timeout returns failure", ok is False)
check("timeout does NOT trip the breaker", not _yt_breaker_open())
check("timeout does NOT mark a wave",
      download_hit_block_wave() is False)
check("timeout reason says took too long",
      "took too long" in result.lower(), result[:80])

# ── 5. Capped wrapper: real fork behavior ─────────────────────────────────
# 5a. Success passes through.
with patch.object(yds, '_download_video_with_client',
                  return_value=(True, ("youtube_x.mp4", "done"))):
    out = _download_video_with_client_capped("u", "x", "t", "android")
check("capped wrapper passes success through",
      out == (True, ("youtube_x.mp4", "done")), str(out))

# 5b. Child exceptions are re-raised with their type intact.
with patch.object(yds, '_download_video_with_client',
                  side_effect=yt_dlp.utils.DownloadError("boom")):
    try:
        _download_video_with_client_capped("u", "x", "t", "android")
        raised = None
    except Exception as e:
        raised = e
check("capped wrapper re-raises child DownloadError",
      isinstance(raised, yt_dlp.utils.DownloadError), repr(raised))


# 5c. A stuck child is hard-killed at the cap (patched to 2s for the test).
def sleepy(url, video_id, tmpl, client):
    time.sleep(30)
    return (True, ("never", "never"))


old_cap = yds._VIDEO_CLIENT_TIMEOUT_SECS
yds._VIDEO_CLIENT_TIMEOUT_SECS = 2
try:
    with patch.object(yds, '_download_video_with_client', sleepy):
        t0 = time.time()
        try:
            _download_video_with_client_capped("u", "x", "t", "android")
            terr = None
        except TimeoutError as e:
            terr = e
        dt = time.time() - t0
finally:
    yds._VIDEO_CLIENT_TIMEOUT_SECS = old_cap

check("stuck child raises TimeoutError", isinstance(terr, TimeoutError),
      repr(terr))
check("kill happens near the cap, not after the sleep",
      dt < 20, f"{dt:.1f}s")

print(f"\nround-33: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
