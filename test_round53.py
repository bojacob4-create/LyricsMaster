"""Round 53: /newmusic bare path goes deep + header/footer de-noised.

User finding (2026-09-25): bare /newmusic repeated the same songs every
2 calls — round 52 had deepened only the genre slices; the bare path still
walked the 10-song trending list.  This round gives the bare path the full
US chart (~90 deep, deduped by artist) and removes the noisy
"Fresh releases first, then what's charting:" header line and the
"Freshest first — ..." footer line.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import discovery_service as ds
from services.artist_service import get_trending_songs, get_us_chart_deep

UID = 999001  # fake user, keeps rotation memory isolated from real users


def _key(s):
    return (str(s.get("artist", "")).lower().strip(),
            str(s.get("song", "")).lower().strip())


def test_bare_pool_is_deep():
    cands, is_live, gkey = ds._get_new_music_candidates(None, 5)
    deep = get_us_chart_deep()
    assert is_live, "bare path should be live when the chart is up"
    assert len(cands) == len(deep), "bare path should serve the full deep chart"
    assert len(cands) > 10, f"bare pool not deeper than the old 10-rail: {len(cands)}"
    assert gkey == ""
    print(f"  bare pool depth: {len(cands)} (was 10, live={is_live})")


def test_bare_rotation_no_repeats():
    cands, _, _ = ds._get_new_music_candidates(None, 5)
    clean_calls = len(cands) // 5  # full windows before the cycle boundary
    assert clean_calls >= 2, "pool too shallow to test rotation"
    seen = []
    for _ in range(clean_calls):
        songs, is_live = ds.get_new_music(None, 5, UID)
        assert is_live and len(songs) == 5
        seen.extend(_key(s) for s in songs)
    assert len(set(seen)) == len(seen), (
        f"repeats within {clean_calls} calls: {len(seen) - len(set(seen))} dupes")
    print(f"  {clean_calls} consecutive bare calls -> "
          f"{len(seen)}/{len(seen)} unique")


def test_trending_contract_unchanged():
    songs, is_live = get_trending_songs()
    assert len(songs) == 10, f"/trending slice changed: {len(songs)}"
    print("  get_trending_songs still returns exactly 10 (/trending untouched)")


def test_us_chart_deep_shape():
    deep = get_us_chart_deep()
    assert len(deep) > 10, f"deep chart not deeper than old rail: {len(deep)}"
    artists = [s["artist"].lower().strip() for s in deep]
    assert len(set(artists)) == len(artists), "deep chart has dup artists"
    assert all(s["artist"] and s["song"] for s in deep)
    print(f"  get_us_chart_deep: {len(deep)} unique-artist songs")


def test_genre_path_untouched():
    cands, is_live, gkey = ds._get_new_music_candidates("pop", 5)
    assert is_live and gkey == "pop"
    assert len(cands) > 10, f"genre path regressed: {len(cands)}"
    print(f"  genre path still deep: {len(cands)} pop songs")


class _FakeChat:
    def send_action(self, action=None):
        pass


class _FakeMessage:
    def __init__(self):
        self.chat = _FakeChat()
        self.text = "/newmusic"
        self.sent = []

    def reply_text(self, text, **kwargs):
        self.sent.append(text)


class _FakeUser:
    id = UID


class _FakeUpdate:
    def __init__(self):
        self.effective_user = _FakeUser()
        self.message = _FakeMessage()


class _FakeContext:
    args = []


def _run_handler(monkey=None):
    import handlers
    if monkey:
        monkey()
    upd, ctx = _FakeUpdate(), _FakeContext()
    handlers.newmusic_command(upd, ctx)
    assert upd.message.sent, "handler sent nothing"
    return upd.message.sent[0]


def test_header_footer_clean_live():
    text = _run_handler()
    assert "Fresh releases first" not in text, "header noise still present"
    assert "Freshest first" not in text, "footer noise still present"
    assert "60 days" not in text, "footer noise still present"
    assert text.startswith("🔥 *Hot Right Now*"), f"bad header: {text[:40]!r}"
    assert "↳ Charting now on Apple Music" not in text, "note noise back"
    print("  live card: clean header, no footer, no repeated notes")


def test_fallback_header_stays_honest():
    orig_deep = ds.get_us_chart_deep
    orig_trending = ds.get_trending_songs
    ds.get_us_chart_deep = lambda: []
    ds.get_trending_songs = lambda: ([], False)
    try:
        text = _run_handler()
    finally:
        ds.get_us_chart_deep = orig_deep
        ds.get_trending_songs = orig_trending
    assert "Popular picks while the live chart refreshes" in text, (
        "fallback honesty label lost")
    assert "Freshest first" not in text
    print("  fallback card: honest label kept, footer gone")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            print(f"{t.__name__} ...")
            t()
            print("  OK")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
