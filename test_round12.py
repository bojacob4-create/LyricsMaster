"""Round 12 tests — MP3 fail-fast wave detection. No network, no real downloads.

Covers the "fail fast" improvement:
  1. _is_soft_wave_error classifies stall/timeout/format errors (but not
     hard block errors or DRM walls)
  2. Two consecutive soft failures across different candidates trip the
     YouTube breaker and abort the remaining attempts (fail fast, ~2 min
     instead of ~5) — and the queued auto-retry path picks it up
  3. A single soft failure followed by success still delivers (no false abort)
  4. A hard block error still trips the breaker immediately (old behavior)

Run: ../venv/bin/python test_round12.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"[FAIL] {name} {detail}")


from services import youtube_downloader_service as yds

# ── 1. soft-wave classifier ──────────────────────────────────────────────
check("soft: stall timeout",
      yds._is_soft_wave_error(TimeoutError("download stalled (45s budget)")))
check("soft: read timeout",
      yds._is_soft_wave_error(Exception("ERROR: \\[download\\] Got error: "
                                        "The read operation timed out. "
                                        "Giving up after 2 retries")))
check("soft: format not available",
      yds._is_soft_wave_error(Exception("ERROR: [youtube] V2G8ESoDXm8: "
                                        "Requested format is not available.")))
check("not soft: DRM wall",
      not yds._is_soft_wave_error(Exception("[soundcloud] 123: "
                                            "This video is DRM protected")))
check("not soft: hard bot-block (handled by _is_block_error instead)",
      not yds._is_soft_wave_error(Exception("sign in to confirm "
                                            "you're not a bot")))
check("not soft: random error",
      not yds._is_soft_wave_error(Exception("disk full")))


def _canned_entries():
    return [
        {"title": "SZA - Saturn (Official Audio)", "uploader": "SZA",
         "duration": 200, "webpage_url": "https://yt.example/v1"},
        {"title": "SZA - Saturn (Audio)", "uploader": "SZA",
         "duration": 205, "webpage_url": "https://yt.example/v2"},
        {"title": "SZA - Saturn (Lyric Video)", "uploader": "SZA",
         "duration": 198, "webpage_url": "https://yt.example/v3"},
    ]


def _install_mocks(download_behavior):
    """Replace network/download pieces. download_behavior(url, call_no)
    either raises or returns a real temp mp3-sized file path."""
    calls = {"n": 0}
    orig = {}
    for name in ("_sc_search_entries", "_yt_search_entries",
                 "_audius_search_entries", "_expected_duration",
                 "_download_url_to_mp3", "_disk_cache_put",
                 "_winurl_note", "_failure_note"):
        orig[name] = getattr(yds, name)

    yds._sc_search_entries = lambda q, n=8: []
    yds._yt_search_entries = lambda q, n=5: _canned_entries()
    yds._audius_search_entries = lambda q, n=8: []
    yds._expected_duration = lambda a, s: 200

    def fake_dl(url, prefix, label=None):
        calls["n"] += 1
        return download_behavior(url, calls["n"])

    yds._download_url_to_mp3 = fake_dl
    yds._disk_cache_put = lambda key, path: path
    yds._winurl_note = lambda *a: None
    yds._failure_note = lambda *a: None
    yds._YT_BLOCKED_UNTIL = 0.0  # breaker reset
    return orig, calls


def _restore(orig):
    for name, fn in orig.items():
        setattr(yds, name, fn)
    yds._YT_BLOCKED_UNTIL = 0.0


def _big_temp_file():
    fd, path = tempfile.mkstemp(suffix=".mp3")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\0" * (yds._MIN_SONG_BYTES + 100))
    return path


# ── 2. two consecutive soft failures -> breaker trips, attempts abort ────
def always_stall(url, call_no):
    raise TimeoutError("download stalled (45s budget)")

orig, calls = _install_mocks(always_stall)
try:
    ok, result = yds.download_audio_for_song("SZA", "Saturn")
    check("wave: returns failure (not hang)", ok is False)
    check("wave: breaker tripped", yds._yt_breaker_open(),
          "breaker should be open after 2 soft failures")
    check("wave: fail-fast stopped at 2 attempts (not 3+)",
          calls["n"] == 2, f"attempts={calls['n']}")
    check("wave: user gets the 'blocked' message (queues auto-retry)",
          isinstance(result, str) and "blocking downloads" in result,
          str(result)[:80])
finally:
    _restore(orig)

# ── 3. single soft failure then success -> delivers, breaker stays shut ──
def stall_then_ok(url, call_no):
    if call_no == 1:
        raise TimeoutError("download stalled (45s budget)")
    return _big_temp_file()

orig, calls = _install_mocks(stall_then_ok)
try:
    ok, result = yds.download_audio_for_song("SZA", "Saturn")
    check("recover: delivers after one stall", ok is True, str(ok))
    check("recover: breaker NOT tripped by a single stall",
          not yds._yt_breaker_open())
    check("recover: tried exactly 2 candidates", calls["n"] == 2,
          f"attempts={calls['n']}")
finally:
    _restore(orig)

# ── 4. hard block error still trips immediately (old behavior intact) ─────
def hard_block(url, call_no):
    raise Exception("sign in to confirm you're not a bot")

orig, calls = _install_mocks(hard_block)
try:
    ok, result = yds.download_audio_for_song("SZA", "Saturn")
    check("block: returns failure", ok is False)
    check("block: breaker tripped on first hard error",
          yds._yt_breaker_open())
    # Old behavior preserved: hard-block errors raise immediately (no
    # 45s stall), so the loop still walks the remaining candidates —
    # a SoundCloud/Audius entry later in the list can still win.
    check("block: remaining candidates still tried", calls["n"] == 3,
          f"attempts={calls['n']}")
finally:
    _restore(orig)

print(f"\n{'='*60}\nRESULT: {PASS}/{PASS+FAIL} passed")
if FAILURES:
    print("FAILURES:", FAILURES)
sys.exit(1 if FAIL else 0)