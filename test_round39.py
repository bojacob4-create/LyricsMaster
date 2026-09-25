"""Round-39 tests: the command-audit fix round.

Covers the 6 audit findings:
  P1 /translate — googletrans replaced with requests-based gtx translate.
  P2 /daily    — starting the game marks last_started; no re-roll via
                 /daily -> /daily or /daily -> /cancel -> /daily.
  P3 config.py — hardcoded secret-looking TELEGRAM_TOKEN removed.
  P4 /about    — header no longer duplicates "songs about".
  P5 /newmusic — unknown genre gets the /top-style "not found" message
                 instead of blaming the charts.
  P6 /quiz     — an active quiz is no longer presented as a fresh start.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


# ── fakes ──────────────────────────────────────────────────────────────────

class FakeMessage:
    def __init__(self):
        self.replies = []
        self.text = ""

    def reply_text(self, text, **kw):
        self.replies.append(text)
        m = FakeMessage()
        m.edited = []
        orig_edit = m.edit_text

        def edit_text(t, **k):
            m.edited.append(t)
            return orig_edit(t, **k)
        m.edit_text = edit_text
        return m

    def edit_text(self, text, **kw):
        pass

    @property
    def chat(self):
        class C:
            def send_action(self, action=None):
                pass
        return C()


class FakeUpdate:
    def __init__(self, user_id=777):
        self.message = FakeMessage()
        self._uid = user_id

    @property
    def effective_user(self):
        class U:
            id = self._uid
        return U()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


# ── P1: translate backend ──────────────────────────────────────────────────

def t_p1_translate_live():
    print("-- P1: requests-based translate works live --")
    from services import translator_service as ts
    out = ts.translate_chunk("Hello, how are you?", "es")
    check("spanish chunk translates", bool(out) and "hola" in out.lower())
    out2 = ts.translate_chunk("Good night", "fr")
    check("french chunk translates", bool(out2) and "bonne" in out2.lower())


def t_p1_translate_text_multichunk():
    print("-- P1: translate_text chunks long input --")
    from services import translator_service as ts
    long_text = ("The quick brown fox jumps over the lazy dog. " * 60).strip()
    assert len(long_text) > 1000, "test needs multi-chunk input"
    out = ts.translate_text(long_text, "de")
    check("multi-chunk german translation", bool(out) and len(out) > 100)


def t_p1_translate_helpers():
    print("-- P1: language helpers intact --")
    from services import translator_service as ts
    check("get_language_code('spanish')", ts.get_language_code("spanish") == "es")
    check("get_language_code('es')", ts.get_language_code("es") == "es")
    check("get_language_display('es')", ts.get_language_display("es") == "Spanish")
    check("translate_to_arabic works",
          bool(ts.translate_to_arabic("Hello")) )
    check("empty text -> None", ts.translate_chunk("", "es") is None)
    check("no googletrans remnants",
          not hasattr(ts, "get_translator") and "googletrans" not in sys.modules)


def t_p1_cache_success_only():
    print("-- P1: success-only cache --")
    from services import translator_service as ts
    ts._chunk_cache.clear()
    a = ts.translate_chunk("Cache probe sentence", "it")
    check("first call translates", bool(a))
    check("result cached", ("Cache probe sentence", "it") in ts._chunk_cache)
    b = ts.translate_chunk("Cache probe sentence", "it")
    check("cached call identical", a == b)


# ── P2: daily double-start ─────────────────────────────────────────────────

def _isolate_daily():
    from services import fun_service as fs
    tmp = tempfile.mkdtemp()
    fs.DAILY_PATH = os.path.join(tmp, "fun_daily.json")
    return fs


def t_p2_start_marks_played():
    print("-- P2: starting marks the day as played --")
    fs = _isolate_daily()
    uid = 4242
    st = fs.get_daily_status(uid, today="2026-09-25")
    check("can play before start", st["can_play"] is True)
    fs.mark_daily_started(uid, today="2026-09-25")
    st = fs.get_daily_status(uid, today="2026-09-25")
    check("cannot play after start", st["can_play"] is False)
    st = fs.get_daily_status(uid, today="2026-09-26")
    check("can play next day", st["can_play"] is True)


def t_p2_streak_still_computed_on_finish():
    print("-- P2: streaks still computed at finish --")
    fs = _isolate_daily()
    uid = 4343
    fs.mark_daily_started(uid, today="2026-09-25")
    res = fs.record_daily_play(uid, 4, 5, today="2026-09-25")
    check("finish after start records streak 1", res["streak"] == 1)
    fs.mark_daily_started(uid, today="2026-09-26")
    res = fs.record_daily_play(uid, 5, 5, today="2026-09-26")
    check("consecutive day streak 2", res["streak"] == 2)
    check("day after finish cannot replay",
          fs.get_daily_status(uid, today="2026-09-26")["can_play"] is False)


def t_p2_daily_command_no_reroll():
    print("-- P2: /daily twice -> second is refused --")
    import handlers
    from services import fun_service as fs
    tmp = tempfile.mkdtemp()
    fs.DAILY_PATH = os.path.join(tmp, "fun_daily.json")
    uid = 4444
    # Stub question building so no network is needed.
    orig_make = handlers.make_daily_questions

    def _stub_questions(n=5):
        return [{
            "qtype": "guess_artist",
            "snippet": f"test lyric line {i}",
            "options": [{"artist": f"Artist {c}"} for c in "ABCD"],
            "answer": "A", "artist": "X", "song": "Y",
        } for i in range(5)]
    handlers.make_daily_questions = _stub_questions
    try:
        u1 = FakeUpdate(uid)
        handlers.daily_command(u1, FakeContext())
        first_replies = list(u1.message.replies)
        check("first /daily starts game",
              any("Daily Challenge" in r for r in first_replies))
        check("session active", uid in handlers.active_daily)

        u2 = FakeUpdate(uid)
        handlers.daily_command(u2, FakeContext())
        second_text = "\n".join(u2.message.replies)
        check("second /daily refused",
              "already played today" in second_text)
        check("original session untouched",
              handlers.active_daily[uid]["idx"] == 0)
    finally:
        handlers.make_daily_questions = orig_make
        handlers.active_daily.pop(uid, None)


# ── P3: config.py secret ───────────────────────────────────────────────────

def t_p3_no_hardcoded_token():
    print("-- P3: config.py has no hardcoded token --")
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "config.py")).read()
    check("TELEGRAM_TOKEN gone from config.py", "TELEGRAM_TOKEN" not in src)
    import config
    check("config still imports", hasattr(config, "Config"))


# ── P4: about header ───────────────────────────────────────────────────────

def t_p4_about_header():
    print("-- P4: /about header cleaning --")
    import handlers
    cases = [
        ("songs about heartbreak", "heartbreak"),
        ("song about summer nights", "summer nights"),
        ("SONGS ABOUT starting over", "starting over"),
        ("  songs   about   love  ", "love"),
        ("heartbreak", "heartbreak"),
        ("songs about", "songs about"),  # degenerate: keep original, never empty
    ]
    for raw, expected in cases:
        got = handlers._clean_about_query(raw)
        check(f"clean {raw!r} -> {expected!r}", got == expected)


# ── P5: newmusic genre ─────────────────────────────────────────────────────

def t_p5_genre_resolver():
    print("-- P5: newmusic genre resolver --")
    from services.discovery_service import (resolve_newmusic_genre,
                                            get_newmusic_genres)
    check("pop resolves", resolve_newmusic_genre("pop") == "pop")
    check("alias k-pop resolves", resolve_newmusic_genre("k-pop") == "kpop")
    check("alias hip hop resolves", resolve_newmusic_genre("hip hop") == "rap")
    check("zzzgenre unknown", resolve_newmusic_genre("zzzgenre") is None)
    check("empty unknown", resolve_newmusic_genre("") is None)
    check("genre list non-empty", len(get_newmusic_genres()) >= 5)


def t_p5_newmusic_bad_genre_message():
    print("-- P5: /newmusic zzzgenre message --")
    import handlers
    u = FakeUpdate(555)
    handlers.newmusic_command(u, FakeContext(args=["zzzgenre"]))
    text = "\n".join(u.message.replies)
    check("says genre not found", 'not found' in text.lower())
    check("does not blame charts", "charts right now" not in text.lower())
    check("lists alternatives", "pop" in text.lower())


# ── P6: quiz already-playing ───────────────────────────────────────────────

def t_p6_quiz_no_fake_restart():
    print("-- P6: /quiz during active quiz --")
    import handlers
    uid = 666
    handlers.active_quizzes[uid] = {
        "state": "active",
        "current_question": {
            "qtype": "guess_artist",
            "snippet": "test lyric line",
            "options": [{"artist": f"Artist {c}"} for c in "ABCD"],
            "answer": "A", "artist": "Art", "song": "Song",
        },
        "score": 2, "total_questions": 3, "mode": "multiple_choice",
        "used_songs": [], "streak": 1, "best_streak": 1,
    }
    try:
        u = FakeUpdate(uid)
        handlers.quiz_command(u, FakeContext())
        text = "\n".join(u.message.replies)
        check("already-playing framing", "already in a quiz" in text.lower())
        check("no fresh Let's Go header", "Let's Go" not in text)
        check("current question reshown", "test lyric line" in text)
        check("score preserved",
              handlers.active_quizzes[uid]["score"] == 2)
    finally:
        handlers.active_quizzes.pop(uid, None)


if __name__ == "__main__":
    t_p1_translate_live()
    t_p1_translate_text_multichunk()
    t_p1_translate_helpers()
    t_p1_cache_success_only()
    t_p2_start_marks_played()
    t_p2_streak_still_computed_on_finish()
    t_p2_daily_command_no_reroll()
    t_p3_no_hardcoded_token()
    t_p4_about_header()
    t_p5_genre_resolver()
    t_p5_newmusic_bad_genre_message()
    t_p6_quiz_no_fake_restart()
    print(f"\n==== round39: {PASS} passed, {FAIL} failed ====")
    if FAILURES:
        print("FAILURES:", FAILURES)
    sys.exit(1 if FAIL else 0)
