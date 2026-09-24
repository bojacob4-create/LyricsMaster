"""Round-16 tests: /download quality adapts to Telegram's 50MB cap.

The old code hard-capped every video at 720p and then deleted the file if
it came out over 50MB ("try a shorter video"). The new code lets yt-dlp
pick the best quality that fits under ~45MB: short videos get 1080p when
it fits, long ones drop to whatever fits, and the 50MB check stays as a
safety net. Also: file picking now ignores temp/leftover files and picks
the largest finished match instead of matches[0].
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.youtube_downloader_service import (
    _DOWNLOAD_FORMAT,
    _pick_downloaded_file,
)

passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok    {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {detail}")

# ── 1. Format selector: adaptive, no hard resolution cap ──────────────────
check("format: no hard 720p ceiling", "height<=720" not in _DOWNLOAD_FORMAT,
      _DOWNLOAD_FORMAT)
check("format: prefers best video under 40M",
      _DOWNLOAD_FORMAT.startswith("bestvideo[filesize<40M]"),
      _DOWNLOAD_FORMAT)
check("format: audio stream capped so merge stays under ~45M",
      "bestaudio[filesize<5M]" in _DOWNLOAD_FORMAT, _DOWNLOAD_FORMAT)
check("format: single-file fallback under 45M",
      "best[filesize<45M]" in _DOWNLOAD_FORMAT, _DOWNLOAD_FORMAT)
check("format: unrestricted best kept as last-resort fallback",
      _DOWNLOAD_FORMAT.rstrip().endswith("bestvideo+bestaudio/best"),
      _DOWNLOAD_FORMAT)
# Sanity: the tightest constrained pick (40M video + 5M audio) leaves a
# clear margin under Telegram's 50MB cap.
check("format: constrained picks sum under 50MB", 40 + 5 < 50)

# ── 2. _pick_downloaded_file ─────────────────────────────────────────────
tmp = tempfile.mkdtemp()
old_cwd = os.getcwd()
os.chdir(tmp)
try:
    vid = "abc123XYZ"

    # No files at all -> None
    check("pick: no files -> None", _pick_downloaded_file(vid) is None)

    # Leftover temp files are ignored
    open(f"youtube_{vid}.mp4.part", "w").write("x" * 100)
    open(f"youtube_{vid}.mp4.ytdl", "w").write("x" * 100)
    check("pick: temp files ignored", _pick_downloaded_file(vid) is None)

    # Finished file is found
    open(f"youtube_{vid}.mp4", "w").write("x" * 500)
    got = _pick_downloaded_file(vid)
    check("pick: finished file found",
          got is not None and got.endswith(f"youtube_{vid}.mp4"), repr(got))

    # A stale leftover from an earlier run must NOT shadow the new file:
    # the largest finished match wins (the real merged mp4 is the biggest).
    open(f"youtube_{vid}.webm", "w").write("x" * 100)
    got = _pick_downloaded_file(vid)
    check("pick: largest match wins over stale leftover",
          got is not None and got.endswith(f"youtube_{vid}.mp4"), repr(got))

    # Different video id does not leak in
    check("pick: other video id ignored",
          _pick_downloaded_file("other999") is None)
finally:
    os.chdir(old_cwd)

# ── 3. 50MB safety net still present in the downloader ───────────────────
# (Round 30 moved the download body into _download_video_with_client; the
# checks follow the code, not the old function name.)
import inspect
from services import youtube_downloader_service as yds
src = inspect.getsource(yds._download_video_with_client)
check("downloader: 50MB post-download guard retained",
      "50 * 1024 * 1024" in src)
check("downloader: uses _pick_downloaded_file (not matches[0])",
      "_pick_downloaded_file(video_id)" in src and "matches[0]" not in src)
check("downloader: uses adaptive _DOWNLOAD_FORMAT",
      "'format': _DOWNLOAD_FORMAT" in src)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
