"""Round-30 tests: /download rotates YouTube player clients.

YouTube's bot-check ("sign in to confirm you're not a bot") flaps per
player client — the web player can be challenged while android/ios sail
through on the same IP.  download_youtube_video() now tries
_YT_CLIENT_ATTEMPTS one client per attempt (same tuple the MP3 path
already uses):

- a bot-check on one client rotates to the next instead of failing;
- permanent failures (private/age-gated/...) stop the rotation at once;
- the shared breaker only trips (and the request only queues) when EVERY
  client hits a hard block error — one challenged client no longer queues.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp
import services.youtube_downloader_service as yds
from services.youtube_downloader_service import (
    download_youtube_video, download_hit_block_wave,
    _is_permanent_video_error, _YT_CLIENT_ATTEMPTS,
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
        if b == 'toolong':
            return {'duration': 9999, 'title': 'Long', 'uploader': 'U'}
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


def clients_used():
    return [o['extractor_args']['youtube']['player_client'][0]
            for o in FakeYDL.instances]


def run(url=URL):
    with patch.object(yds.yt_dlp, 'YoutubeDL', FakeYDL):
        return download_youtube_video(url)


def bot_err():
    return yt_dlp.utils.DownloadError(
        "Sign in to confirm you're not a bot")


# ── 1. First attempt uses android with the extractor arg set ────────────────
reset()
ok, payload = run()
check("success on first client",
      ok is True and payload[0].endswith('.mp4')
      and 'Downloaded!' in payload[1], str(payload)[:80])
check("extractor_args carries player_client=android",
      FakeYDL.instances[0]['extractor_args'] ==
      {'youtube': {'player_client': ['android']}},
      str(FakeYDL.instances[0].get('extractor_args')))
check("no breaker, no wave on success",
      not yds._yt_breaker_open() and not download_hit_block_wave())

# ── 2. Bot-check on android rotates to web and still succeeds ───────────────
reset({'android': bot_err()})
ok, payload = run()
check("rotation succeeds after android bot-check", ok is True, str(ok))
check("tried android then web", clients_used() == ['android', 'web'],
      str(clients_used()))
check("single challenged client does NOT trip the breaker",
      not yds._yt_breaker_open() and not download_hit_block_wave())

# ── 3. All clients blocked -> wave verdict + breaker trips ──────────────────
reset({'android': bot_err(), 'web': bot_err(), 'ios': bot_err()})
ok, notice = run()
check("all blocked: download fails", ok is False)
check("all blocked: wave verdict set", download_hit_block_wave())
check("all blocked: breaker tripped", yds._yt_breaker_open())
check("all blocked: honest bot-check reason",
      "bot check" in notice, notice[:120])
check("all clients tried", clients_used() == list(_YT_CLIENT_ATTEMPTS),
      str(clients_used()))

# ── 4. Permanent failure stops the rotation at once ─────────────────────────
reset({'android': yt_dlp.utils.DownloadError("Private video")})
ok, notice = run()
check("private video: fails", ok is False)
check("private video: no rotation", len(FakeYDL.instances) == 1,
      str(len(FakeYDL.instances)))
check("private video: no breaker, no wave",
      not yds._yt_breaker_open() and not download_hit_block_wave())
check("private video: honest reason", "private" in notice.lower(),
      notice[:80])

# ── 5. The bot-check must never count as permanent ───────────────────────────
check("bot-check is NOT permanent",
      not _is_permanent_video_error("sign in to confirm you're not a bot"))
check("'private video' IS permanent",
      _is_permanent_video_error("private video"))
check("'not available' IS permanent",
      _is_permanent_video_error("video not available"))
check("'http error 429' is NOT permanent",
      not _is_permanent_video_error("http error 429"))

# ── 6. Too-long video returns immediately, single attempt ────────────────────
reset({'android': 'toolong'})
ok, notice = run()
check("too long: fails fast", ok is False and "Video Too Long" in notice,
      notice[:60])
check("too long: single attempt, no breaker",
      len(FakeYDL.instances) == 1 and not yds._yt_breaker_open())

# ── 7. Format refused by one client is served by the next ────────────────────
reset({'android': yt_dlp.utils.DownloadError(
    "Requested format is not available")})
ok, payload = run()
check("format rotation succeeds", ok is True, str(ok))
check("format rotation tried two clients",
      clients_used() == ['android', 'web'], str(clients_used()))
check("format rotation: no wave", not download_hit_block_wave())

# ── 8. Invalid URL never touches yt-dlp ─────────────────────────────────────
reset()
ok, notice = run("not a url")
check("invalid URL rejected", ok is False and "Invalid YouTube URL" in notice,
      notice[:60])
check("invalid URL: zero attempts", len(FakeYDL.instances) == 0)

reset()
print(f"\nround30: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
