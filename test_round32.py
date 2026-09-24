"""Round-32 tests: PO-token escalation (mweb) + browser TLS impersonation.

Findings from the Sep-2026 community research the user asked for:
- bgutil-ytdlp-pot-provider (maintained, no login) mints YouTube PO tokens
  for yt-dlp; the official escalation when clients are challenged is the
  'mweb' client with forced token minting (fetch_pot=always — 'auto' misses
  some player requests).
- YouTube tarpits non-browser TLS fingerprints: extractions stall 100s+
  with zero output unless yt-dlp impersonates Chrome (curl_cffi).

Changes under test (both /download video path and MP3 path):
- _YT_CLIENT_ATTEMPTS gains 'mweb' as the final escalation attempt.
- _client_extractor_args() gives mweb fetch_pot=always; other clients keep
  plain player_client (the installed provider auto-mints for them when the
  client's policy requires it).
- Both ydl option sets carry impersonate='chrome'.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_dlp
import services.youtube_downloader_service as yds
from services.youtube_downloader_service import (
    download_youtube_video, _YT_CLIENT_ATTEMPTS, _client_extractor_args,
    _download_url_to_mp3,
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


def bot_err():
    return yt_dlp.utils.DownloadError(
        "Sign in to confirm you're not a bot")


# ── 1. Rotation order & extractor-args helper ─────────────────────────────
check("rotation is (android, web, ios, mweb)",
      _YT_CLIENT_ATTEMPTS == ('android', 'web', 'ios', 'mweb'),
      str(_YT_CLIENT_ATTEMPTS))

check("mweb gets fetch_pot=always",
      _client_extractor_args('mweb') ==
      {'youtube': {'player_client': ['mweb'], 'fetch_pot': ['always']}},
      str(_client_extractor_args('mweb')))

check("android keeps plain player_client (no forced fetch_pot)",
      _client_extractor_args('android') ==
      {'youtube': {'player_client': ['android']}},
      str(_client_extractor_args('android')))

check("web/ios have no forced fetch_pot",
      'fetch_pot' not in _client_extractor_args('web')['youtube']
      and 'fetch_pot' not in _client_extractor_args('ios')['youtube'])


# ── 2. Video path: challenged android/web/ios escalate to mweb ────────────
reset({'android': bot_err(), 'web': bot_err(), 'ios': bot_err(),
       'mweb': 'ok'})
with patch.object(yds.yt_dlp, 'YoutubeDL', FakeYDL):
    ok, _ = download_youtube_video(URL)
clients = [o['extractor_args']['youtube']['player_client'][0]
           for o in FakeYDL.instances]
check("all challenged -> tries all four clients in order",
      clients == ['android', 'web', 'ios', 'mweb'], str(clients))
check("mweb escalation succeeds the download", ok is True)

mweb_opts = FakeYDL.instances[3]
check("mweb attempt carries fetch_pot=always",
      mweb_opts['extractor_args']['youtube'].get('fetch_pot') == ['always'],
      str(mweb_opts['extractor_args']))
check("video ydl opts impersonate chrome",
      FakeYDL.instances[0].get('impersonate') == 'chrome',
      str(FakeYDL.instances[0].get('impersonate')))
check("video ydl opts enable node JS runtime",
      FakeYDL.instances[0].get('js_runtimes') == ['node'],
      str(FakeYDL.instances[0].get('js_runtimes')))

# ── 3. Video path: android success never reaches mweb (no slowdown) ──────
reset({'android': 'ok'})
with patch.object(yds.yt_dlp, 'YoutubeDL', FakeYDL):
    ok, _ = download_youtube_video(URL)
clients = [o['extractor_args']['youtube']['player_client'][0]
           for o in FakeYDL.instances]
check("healthy android -> single attempt, no mweb slowdown",
      clients == ['android'] and ok is True, str(clients))

# ── 4. MP3 path carries impersonate + client extractor args ───────────────
import tempfile


class FakeYDLmp3:
    instances = []

    def __init__(self, opts):
        self._opts = opts
        FakeYDLmp3.instances.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        with open("mp3test.mp3", 'w') as f:
            f.write('x' * 1024)
        return 0


old_cwd = os.getcwd()
tmp = tempfile.mkdtemp()
os.chdir(tmp)
try:
    with patch.object(yds.yt_dlp, 'YoutubeDL', FakeYDLmp3):
        path = _download_url_to_mp3(
            "https://www.youtube.com/watch?v=mp3test1", "mp3test", "YT")
    opts = FakeYDLmp3.instances[0]
    check("mp3 ydl opts impersonate chrome",
          opts.get('impersonate') == 'chrome',
          str(opts.get('impersonate')))
    check("mp3 ydl opts enable node JS runtime",
          opts.get('js_runtimes') == ['node'],
          str(opts.get('js_runtimes')))
    check("mp3 extractor args use helper (android, no fetch_pot)",
          opts['extractor_args'] == {'youtube': {'player_client': ['android']}},
          str(opts.get('extractor_args')))
    check("mp3 file produced", os.path.exists(path), str(path))
finally:
    os.chdir(old_cwd)

# ── 5. Runtime prerequisites present in the venv ──────────────────────────
try:
    import yt_dlp_plugins.extractor.getpot_bgutil_http  # noqa
    check("bgutil PO-token provider plugin installed", True)
except ImportError as e:
    check("bgutil PO-token provider plugin installed", False, str(e))

try:
    import curl_cffi  # noqa
    check("curl_cffi installed (needed for impersonate)", True)
except ImportError as e:
    check("curl_cffi installed (needed for impersonate)", False, str(e))

import importlib.metadata
try:
    v = importlib.metadata.version('bgutil-ytdlp-pot-provider')
    check("bgutil plugin version is 2.0.0", v == '2.0.0', v)
except importlib.metadata.PackageNotFoundError as e:
    check("bgutil plugin version is 2.0.0", False, str(e))

print(f"\nround-32: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
