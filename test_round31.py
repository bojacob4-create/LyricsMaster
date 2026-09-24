"""Round-31 tests: /download misread a YouTube block as "video not available".

Production 2026-09-24 (Tyla - Water official video): the android client got
the format list and started downloading, then YouTube killed the TCP
connection mid-download ("Remote end closed connection without response");
web/ios refused the format.  Two classification gaps made the bot lie:

1. "Remote end closed connection" / "Connection reset" was not in the
   block-error hints, so the wave detector missed YouTube's other mask
   for the same IP block (18 min earlier the same video got the classic
   "sign in to confirm you're not a bot").
2. The user-facing reason was picked from the LAST client's error only,
   so ios's "Requested format is not available" matched the "not
   available" branch — even though the rotation itself treats a format
   refusal as non-permanent.

Fix: the connection-kill family counts as a block error; the final reason
prefers the most informative client error (permanent > block > format);
and the "requested format" branch is checked before "not available".
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp
import services.youtube_downloader_service as yds
from services.youtube_downloader_service import (
    download_youtube_video, download_hit_block_wave,
    _is_block_error, _is_block_error_msg, _is_permanent_video_error,
    _YT_CLIENT_ATTEMPTS,
)

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


URL = "https://www.youtube.com/watch?v=testvid1234"
DUMMY = "youtube_testvid1234.mp4"


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL; behavior is scripted per client."""
    instances = []
    behaviors = {}

    def __init__(self, opts):
        self._opts = opts
        FakeYDL.instances.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _client(self):
        return self._opts['extractor_args']['youtube']['player_client'][0]

    def extract_info(self, url, download=False):
        b = FakeYDL.behaviors.get(self._client(), 'ok')
        if isinstance(b, BaseException):
            raise b
        return {'duration': 125, 'title': 'T', 'uploader': 'U',
                'view_count': 42}

    def download(self, urls):
        b = FakeYDL.behaviors.get(self._client(), 'ok')
        if isinstance(b, BaseException):
            raise b
        with open(DUMMY, 'w') as f:
            f.write('x' * 1024)
        return 0


def reset(behaviors=None):
    FakeYDL.instances = []
    FakeYDL.behaviors = behaviors or {}
    yds._YT_BLOCKED_UNTIL = 0.0
    if os.path.exists(DUMMY):
        os.remove(DUMMY)


def run(url=URL):
    with patch.object(yds.yt_dlp, 'YoutubeDL', FakeYDL):
        return download_youtube_video(url)


def clients_used():
    return [o['extractor_args']['youtube']['player_client'][0]
            for o in FakeYDL.instances]


def conn_reset_err():
    return yt_dlp.utils.DownloadError(
        "ERROR: [download] Got error: Remote end closed connection "
        "without response. Giving up after 3 retries")


def format_err():
    return yt_dlp.utils.DownloadError("Requested format is not available")


# ── 1. Connection-kill family counts as a block error ───────────────────────
check("remote-end-closed is a block error",
      _is_block_error(conn_reset_err()))
check("'connection reset by peer' is a block error (msg form)",
      _is_block_error_msg("error: connection reset by peer"))
check("'connection aborted' is a block error (msg form)",
      _is_block_error_msg("connection aborted by remote host"))
check("classic bot-check still a block error",
      _is_block_error_msg("sign in to confirm you're not a bot"))
check("format refusal still NOT a hard block",
      not _is_block_error_msg("requested format is not available"))
check("format refusal still NOT permanent",
      not _is_permanent_video_error("requested format is not available"))

# ── 2. Production reproduction: connection-kill + format refusals ────────────
# android got the format list and started downloading (so the video EXISTS);
# web/ios refused the format.  Must NOT say "not available".
reset({'android': conn_reset_err(), 'web': format_err(),
       'ios': format_err()})
ok, notice = run()
check("prod case: download fails", ok is False)
check("prod case: tried all three clients",
      clients_used() == list(_YT_CLIENT_ATTEMPTS), str(clients_used()))
check("prod case: never claims 'not available'",
      "not available" not in notice.lower()
      and "region-locked" not in notice.lower(), notice[:150])
check("prod case: honest blocked reason",
      "YouTube blocked the download" in notice, notice[:150])
check("prod case: single-client block does not queue",
      not download_hit_block_wave() and not yds._yt_breaker_open())

# ── 3. Block error preferred over the last client's format refusal ──────────
reset({'android': yt_dlp.utils.DownloadError(
           "Sign in to confirm you're not a bot"),
       'web': format_err(), 'ios': format_err()})
ok, notice = run()
check("mixed: block error wins the reason",
      "bot check" in notice, notice[:150])
check("mixed: no 'not available' lie", "not available" not in notice.lower(),
      notice[:150])

# ── 4. Permanent error still wins over an earlier block ─────────────────────
reset({'android': yt_dlp.utils.DownloadError(
           "Sign in to confirm you're not a bot"),
       'web': yt_dlp.utils.DownloadError("Private video")})
ok, notice = run()
check("permanent wins: private reason", "private" in notice.lower(),
      notice[:100])
check("permanent wins: rotation stops", clients_used() == ['android', 'web'],
      str(clients_used()))
check("permanent wins: no breaker, no wave",
      not yds._yt_breaker_open() and not download_hit_block_wave())

# ── 5. All clients connection-killed -> wave verdict + breaker trips ─────────
reset({'android': conn_reset_err(), 'web': conn_reset_err(),
       'ios': conn_reset_err()})
ok, notice = run()
check("all killed: download fails", ok is False)
check("all killed: wave verdict set", download_hit_block_wave())
check("all killed: breaker tripped", yds._yt_breaker_open())

# ── 6. Format refusal on ALL clients -> capability reason, not "gone" ───────
reset({'android': format_err(), 'web': format_err(), 'ios': format_err()})
ok, notice = run()
check("all-format: honest capability reason",
      "No compatible format available" in notice, notice[:150])
check("all-format: not 'not available'",
      "region-locked" not in notice.lower(), notice[:150])
check("all-format: no breaker, no wave",
      not yds._yt_breaker_open() and not download_hit_block_wave())

# ── 7. Genuine unavailability still reported honestly ────────────────────────
reset({'android': yt_dlp.utils.DownloadError("Video unavailable")})
ok, notice = run()
check("genuine: 'not available' reason kept",
      "not available" in notice.lower(), notice[:150])
check("genuine: rotation stops at once", len(FakeYDL.instances) == 1,
      str(len(FakeYDL.instances)))
check("genuine: no breaker, no wave",
      not yds._yt_breaker_open() and not download_hit_block_wave())

# ── 8. Bot-check wave still queues via the verdict ───────────────────────────
def bot_err():
    return yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")

reset({'android': bot_err(), 'web': bot_err(), 'ios': bot_err()})
ok, notice = run()
check("wave: verdict set for queueing", download_hit_block_wave())
check("wave: breaker tripped", yds._yt_breaker_open())

reset()
print(f"\nround31: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
