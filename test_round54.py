"""Round 54: /trending becomes velocity ("Biggest Climbers").

True trending = what's rising, not what's on top.  The bot persists one
dated US-chart snapshot per day and ranks position deltas vs ~7 days ago.
Cold start (fewer than 2 snapshots >=24h apart) honestly falls back to the
static top-10 instead of fake climbers.
"""
import sys
import os
import json
import datetime
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import artist_service as a

TMP = tempfile.mkdtemp(prefix="r54_snaps_")
a._history_base_dir = lambda: TMP  # isolate from real history
a._CHART_SNAP_KEEP = 14


def _write_snap(date, songs, sub="us"):
    d = os.path.join(TMP, sub)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{date}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"date": date,
                   "songs": [{"artist": ar, "song": so}
                             for ar, so in songs]}, f)


def _songs(prefix, n):
    return [(f"Artist{i}", f"{prefix} Song{i}") for i in range(1, n + 1)]


def _clear():
    for root, dirs, files in os.walk(TMP):
        for f in files:
            if f.endswith(".json"):
                os.remove(os.path.join(root, f))


def _us_files():
    d = os.path.join(TMP, "us")
    return sorted(f for f in os.listdir(d) if f.endswith(".json")) \
        if os.path.isdir(d) else []


def test_snapshot_write_and_shape():
    _clear()
    raw = [{"artist": "A", "song": "S1"}, {"artist": "B", "song": "S2"}]
    a._snapshot_us_chart(raw)
    a._snapshot_us_chart(raw)  # idempotent per day
    files = _us_files()
    assert len(files) == 1, f"expected 1 daily file, got {files}"
    data = json.load(open(os.path.join(TMP, "us", files[0]),
                          encoding="utf-8"))
    assert data["date"] == datetime.date.today().strftime("%Y-%m-%d")
    assert data["songs"] == raw
    print("  snapshot: 1 dated file/day, correct shape")


def test_velocity_ranking_and_new():
    _clear()
    today = datetime.date.today()
    ref_d = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    _write_snap(ref_d, _songs("Ref", 10))
    # latest: Ref Song10 was #10 -> #2 (+8); Ref Song5 was #5 -> #1 (+4);
    # brand-new debut at #3; Ref Song1 was #1 -> #4 (declined, excluded)
    latest = [("Artist5", "Ref Song5"), ("Artist10", "Ref Song10"),
              ("NewArtist", "Debut Hit"), ("Artist1", "Ref Song1"),
              ("Artist2", "Ref Song2"), ("Artist3", "Ref Song3"),
              ("Artist4", "Ref Song4"), ("Artist6", "Ref Song6"),
              ("Artist7", "Ref Song7"), ("Artist8", "Ref Song8")]
    _write_snap(today.strftime("%Y-%m-%d"), latest)
    climbers, window = a.get_chart_climbers(10)
    assert window == "vs 7 days ago", f"bad label: {window}"
    assert len(climbers) == 3, f"expected 3 climbers, got {len(climbers)}"
    assert climbers[0]["song"] == "Debut Hit" and climbers[0]["move"] == "NEW"
    assert climbers[1]["song"] == "Ref Song10" and climbers[1]["move"] == "▲8"
    assert climbers[2]["song"] == "Ref Song5" and climbers[2]["move"] == "▲4"
    print("  velocity: NEW first, then ▲8, ▲4; decliner excluded")


def test_window_label_honest_when_short():
    _clear()
    today = datetime.date.today()
    _write_snap((today - datetime.timedelta(days=2)).strftime("%Y-%m-%d"),
                _songs("Old", 10))
    _write_snap(today.strftime("%Y-%m-%d"), _songs("New", 10))
    climbers, window = a.get_chart_climbers(10)
    assert window == "vs 2 days ago", f"bad label: {window}"
    # all 10 are NEW debuts (no key overlap), ranked by current position
    assert all(c["move"] == "NEW" for c in climbers)
    assert climbers[0]["song"] == "New Song1"
    print("  short history: label says 'vs 2 days ago', NEW ranked by pos")


def test_cold_start_single_snapshot():
    _clear()
    _write_snap(datetime.date.today().strftime("%Y-%m-%d"), _songs("Only", 10))
    climbers, window = a.get_chart_climbers(10)
    assert climbers == [] and window is None
    print("  cold start: ([], None) -> handler falls back honestly")


def test_same_day_snapshots_not_enough():
    _clear()
    today = datetime.date.today().strftime("%Y-%m-%d")
    _write_snap(today, _songs("A", 10))
    # only one file can exist per date; simulate a second fetch same day
    a._snapshot_us_chart([{"artist": "X", "song": "Y"}])
    climbers, window = a.get_chart_climbers(10)
    assert climbers == [] and window is None
    print("  same-day re-fetch: still cold start (needs >=24h)")


def test_prune_keeps_14():
    _clear()
    today = datetime.date.today()
    for i in range(20, 0, -1):
        d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        _write_snap(d, _songs("P", 3))
    a._snapshot_us_chart([{"artist": "A", "song": "S"}])
    files = _us_files()
    assert len(files) == 14, f"expected 14 files, got {len(files)}"
    assert files[0] == (today - datetime.timedelta(days=13)).strftime(
        "%Y-%m-%d") + ".json"
    print("  prune: 20 daily files -> newest 14 kept")


def test_format_climbers_escapes():
    text = a.format_climbers(
        [{"artist": "A_B", "song": "C*D", "move": "▲5"},
         {"artist": "E", "song": "F", "move": "NEW"}], "vs 7 days ago")
    assert text.startswith("📈 *Trending — Biggest Climbers*")
    assert "_vs 7 days ago_" in text
    assert "▲5" in text and "🆕" in text
    assert "A\\_B" in text and "C\\*D" in text, "markdown not escaped"
    print("  format: header, badges, markdown-escaped names")


class _FakeChat:
    def send_action(self, action=None):
        pass


class _FakeMessage:
    def __init__(self):
        self.chat = _FakeChat()
        self.sent = []

    def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs))


class _FakeUpdate:
    def __init__(self):
        self.effective_user = type("U", (), {"id": 999002})()
        self.message = _FakeMessage()


def _run_handler(climbers_ret):
    import handlers
    orig = handlers.get_chart_climbers
    handlers.get_chart_climbers = lambda n=10: climbers_ret
    try:
        upd = _FakeUpdate()
        handlers.trending_command(upd, type("C", (), {"args": []})())
    finally:
        handlers.get_chart_climbers = orig
    assert upd.message.sent, "handler sent nothing"
    return upd.message.sent[0]


def test_handler_climbers_path():
    text, kw = _run_handler(
        ([{"artist": "A", "song": "S", "move": "▲12"}], "vs 7 days ago"))
    assert "Biggest Climbers" in text and "▲12" in text
    assert kw.get("parse_mode") == "Markdown"
    print("  handler: climbers path renders velocity card")


def test_handler_fallback_honest():
    import handlers
    orig_trend = handlers.get_trending_songs
    handlers.get_trending_songs = lambda: ([{"artist": "A", "song": "S"}], True)
    try:
        text, kw = _run_handler(([], None))
    finally:
        handlers.get_trending_songs = orig_trend
    assert "Trending Now" in text, "fallback card lost"
    assert "Climber tracking begins" in text, "honest cold-start line lost"
    assert kw.get("parse_mode") is None, "fallback must not use Markdown"
    print("  handler: cold start falls back with honest label")


def test_genre_snapshot_hook():
    _clear()
    orig_fetch = a._fetch_apple_genre_chart
    calls = []

    def fake_fetch(gid, country='us', limit=100):
        calls.append((gid, country))
        return [{"artist": "GA", "song": "GS1"},
                {"artist": "GB", "song": "GS2"}]

    a._fetch_apple_genre_chart = fake_fetch
    a._genre_chart_cache.clear()
    try:
        songs = a._get_cached_genre_chart('14', 'us')   # fresh -> snapshot
        assert songs and len(songs) == 2
        songs2 = a._get_cached_genre_chart('14', 'us')  # cache hit
        assert songs2 == songs
        assert len(calls) == 1, "cache hit must not refetch"
    finally:
        a._fetch_apple_genre_chart = orig_fetch
        a._genre_chart_cache.clear()
    gdir = os.path.join(TMP, "genre", "us_14")
    files = sorted(f for f in os.listdir(gdir) if f.endswith(".json"))
    assert len(files) == 1, f"expected 1 genre snapshot, got {files}"
    data = json.load(open(os.path.join(gdir, files[0]), encoding="utf-8"))
    assert data["songs"][0] == {"artist": "GA", "song": "GS1"}
    print("  genre hook: fresh fetch snapshots once; cache hit is silent")


def test_country_snapshot_generalized():
    _clear()
    a._snapshot_country_chart('kr', [{"artist": "K", "song": "KS"}])
    kdir = os.path.join(TMP, "kr")
    files = [f for f in os.listdir(kdir) if f.endswith(".json")]
    assert len(files) == 1
    # us snapshots still land in the us dir get_chart_climbers reads
    a._snapshot_country_chart('us', [{"artist": "U", "song": "US"}])
    assert len(_us_files()) == 1
    print("  country snapshots: kr + us dirs independent")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    try:
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
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
