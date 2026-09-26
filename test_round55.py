"""Round 55: /mystats v2 — honest stats.

- Genre percentages use the genre-tagged denominator (sum to ~100), not all
  interactions (quiz/emoji taps used to dilute them).
- "Songs explored" counts DISTINCT songs served, not interaction taps.
- Genre display names: rnb -> R&B, hiphop -> Hip-Hop (title() mangled them).
- 10-block bar (1 per 10%) so close genres stay visually distinct.
- Quiz accuracy as correct/answered with %; quiz_wrong is now logged.
- Richer labels: balanced top-two -> "X x Y blend" (checked before "lover"),
  quiz-dominant users -> "Quiz shark".
"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import MagicMock, patch

from services import fun_service as f
import handlers as h

TMP = tempfile.mkdtemp(prefix="r55_stats_")
f.STATS_PATH = os.path.join(TMP, "fun_stats.json")
f.BADGES_PATH = os.path.join(TMP, "fun_badges.json")
f.DAILY_PATH = os.path.join(TMP, "fun_daily.json")


def _reset():
    for p in (f.STATS_PATH, f.BADGES_PATH, f.DAILY_PATH):
        if os.path.exists(p):
            os.remove(p)


def _tagged(uid, genre, n):
    for _ in range(n):
        f.log_interaction(uid, "random", genre=genre)


# ── 1. genre percentages use the genre-tagged denominator ────────────────

def test_genre_denominator():
    _reset()
    u = 5501
    _tagged(u, "afrobeats", 2)
    _tagged(u, "pop", 1)
    # genre-less interactions must NOT dilute the percentages anymore
    f.log_interaction(u, "quiz_start")
    f.log_interaction(u, "emoji")
    f.log_interaction(u, "duel")
    ms = f.get_music_stats(u)
    assert ms["total"] == 6, ms
    top = dict(ms["top"])
    assert top["afrobeats"] == 67, ms["top"]   # 2/3, was 33 under old code
    assert top["pop"] == 33, ms["top"]         # 1/3, was 17 under old code
    assert sum(top.values()) == 100, ms["top"]
    print("  genre pcts: 67/33 of tagged, sum to 100 despite 3 untagged taps")


# ── 2. distinct songs, not taps ──────────────────────────────────────────

def test_distinct_songs():
    _reset()
    u = 5502
    f.log_interaction(u, "recommend", genre="pop",
                      songs=[("Tyla", "Water")])
    f.log_interaction(u, "recommend", genre="pop",
                      songs=[("Tyla", "Water")])          # re-serve: no double count
    f.log_interaction(u, "recommend", genre="pop",
                      songs=[("  tyla ", "WATER  ")])     # normalization dedupes
    f.log_interaction(u, "random", genre="rnb",
                      songs=[("SZA", "Snooze")])
    f.log_interaction(u, "quiz_start")                    # no songs attached
    ms = f.get_music_stats(u)
    assert ms["songs_explored"] == 2, ms
    assert ms["total"] == 5, ms
    print("  songs_explored=2 across 5 interactions (re-serves deduped)")


def test_old_entries_without_songs_key():
    _reset()
    # pre-round-55 entries have no "songs" key — must not break
    with open(f.STATS_PATH, "w", encoding="utf-8") as fh:
        json.dump({"7700": {"genres": {"pop": 2}, "kinds": {"random": 2},
                             "quiz_correct": 0, "total": 2}}, fh)
    ms = f.get_music_stats(7700)
    assert ms["songs_explored"] == 0, ms
    assert ms["total"] == 2 and dict(ms["top"])["pop"] == 100, ms
    print("  old-format entries: songs_explored=0, stats still fine")


# ── 3. display names ─────────────────────────────────────────────────────

def test_genre_display_names():
    assert f.genre_display_name("rnb") == "R&B"
    assert f.genre_display_name("hiphop") == "Hip-Hop"
    assert f.genre_display_name("kpop") == "K-Pop"
    assert f.genre_display_name("pop") == "Pop"
    assert f.genre_display_name("afrobeats") == "Afrobeats"
    print("  rnb->R&B, hiphop->Hip-Hop, others title-cased")


# ── 4. labels ────────────────────────────────────────────────────────────

def test_label_afrobeats_explorer():
    _reset()
    u = 5503
    _tagged(u, "afrobeats", 4)
    _tagged(u, "pop", 1)
    ms = f.get_music_stats(u)
    assert ms["label"] == "🌍 Afrobeats explorer", ms["label"]
    print("  80% afrobeats -> Afrobeats explorer")


def test_label_blend():
    _reset()
    u = 5504
    _tagged(u, "pop", 3)
    _tagged(u, "rnb", 3)
    ms = f.get_music_stats(u)
    assert ms["label"] == "🎧 Pop × R&B blend", ms["label"]
    print("  50/50 pop/rnb -> Pop × R&B blend (display names, not 'Rnb')")


def test_label_blend_boundary():
    _reset()
    u = 5505
    _tagged(u, "pop", 4)   # 40%
    _tagged(u, "rnb", 3)   # 30% -> diff exactly 10 -> blend
    _tagged(u, "rock", 3)
    ms = f.get_music_stats(u)
    assert "blend" in ms["label"], ms["label"]
    u2 = 5506
    _tagged(u2, "pop", 5)  # 50%
    _tagged(u2, "rnb", 2)  # 20% -> diff 30 -> lover, not blend
    _tagged(u2, "rock", 3)
    ms2 = f.get_music_stats(u2)
    assert ms2["label"] == "🎧 Pop lover", ms2["label"]
    print("  diff<=10 -> blend; diff=30 -> Pop lover")


def test_label_rnb_lover_display():
    _reset()
    u = 5507
    _tagged(u, "rnb", 5)   # 56%
    _tagged(u, "pop", 2)
    _tagged(u, "rock", 2)
    ms = f.get_music_stats(u)
    assert ms["label"] == "🎧 R&B lover", ms["label"]
    print("  56% rnb -> 'R&B lover', not 'Rnb lover'")


def test_label_quiz_shark():
    _reset()
    u = 5508
    for g in ["pop", "pop", "pop", "rock", "latin", "country",
              "electronic", "indie"]:
        f.log_interaction(u, "random", genre=g)   # 8 tagged, top 38% < 40
    for _ in range(8):
        f.log_interaction(u, "quiz_correct")
    for _ in range(4):
        f.log_interaction(u, "quiz_wrong")
    ms = f.get_music_stats(u)
    assert ms["quiz_answered"] == 12, ms
    assert ms["label"] == "🎯 Quiz shark", ms["label"]
    print("  12/20 quiz answers, thin genres -> Quiz shark")


def test_label_omnivore_and_new():
    _reset()
    u = 5509
    _tagged(u, "pop", 7)        # 35% — under 40, no blend (diff 15), no quiz
    _tagged(u, "rock", 2)
    _tagged(u, "latin", 3)
    _tagged(u, "country", 4)
    _tagged(u, "electronic", 4)
    ms = f.get_music_stats(u)
    assert ms["label"] == "🎶 Musical omnivore", ms["label"]
    ms0 = f.get_music_stats(999999)
    assert ms0["total"] == 0 and "growing" in ms0["label"], ms0
    print("  no dominance -> omnivore; fresh user -> growing")


# ── 5. quiz accuracy ─────────────────────────────────────────────────────

def test_quiz_accuracy_counts():
    _reset()
    u = 5510
    for _ in range(2):
        f.log_interaction(u, "quiz_correct")
    for _ in range(7):
        f.log_interaction(u, "quiz_wrong")
    ms = f.get_music_stats(u)
    assert ms["quiz_correct"] == 2 and ms["quiz_answered"] == 9, ms
    print("  2 correct / 9 answered tracked")


def test_quiz_answer_wiring():
    _reset()
    u = 5511
    update = MagicMock()
    update.effective_user.id = u
    update.message.text = "B"
    context = MagicMock()
    h.active_quizzes[u] = {"state": "active", "questions": [], "idx": 0}
    try:
        with patch.object(h, "check_answer",
                           return_value=(False, "nope")) as ca, \
             patch.object(h, "_new_badge_lines", return_value=[]):
            h.quiz_answer(update, context)
        ms = f.get_music_stats(u)
        assert ms["quiz_answered"] == 1 and ms["quiz_correct"] == 0, ms
        ca.assert_called_once()
        with patch.object(h, "check_answer",
                           return_value=(True, "yep")), \
             patch.object(h, "_new_badge_lines", return_value=[]):
            h.quiz_answer(update, context)
        ms = f.get_music_stats(u)
        assert ms["quiz_answered"] == 2 and ms["quiz_correct"] == 1, ms
    finally:
        h.active_quizzes.pop(u, None)
    print("  wrong answer -> quiz_wrong; right answer -> quiz_correct")


# ── 6. card rendering ────────────────────────────────────────────────────

def _card_text(uid):
    update = MagicMock()
    update.effective_user.id = uid
    update.message.reply_text = MagicMock()
    h.mystats_command(update, MagicMock())
    args = update.message.reply_text.call_args
    return args[0][0] if args else ""


def test_card_renders_v2():
    _reset()
    u = 5512
    # the reporter's real-world shape: Pop clearly first, R&B close second
    _tagged(u, "pop", 31)
    _tagged(u, "rnb", 26)
    _tagged(u, "afrobeats", 15)
    _tagged(u, "rock", 10)
    for _ in range(2):
        f.log_interaction(u, "quiz_correct")
    for _ in range(7):
        f.log_interaction(u, "quiz_wrong")
    # the recommend call below also tags one pop interaction (as in prod)
    f.log_interaction(u, "recommend", genre="pop",
                      songs=[("Tyla", "Water"), ("Ayra Starr", "Rush")])
    # tagged total = 83 -> pop 39 / rnb 31 / afrobeats 18
    text = _card_text(u)
    assert "🎧 Pop × R&B blend" in text, text
    assert "• Pop — 39%" in text and "• R&B — 31%" in text, text
    assert "• Afrobeats — 18%" in text, text
    pop_line = next(l for l in text.split("\n") if l.startswith("• Pop"))
    afro_line = next(l for l in text.split("\n") if l.startswith("• Afrobeats"))
    assert pop_line.count("🟩") == 3 and pop_line.count("⬜") == 7, pop_line
    assert afro_line.count("🟩") == 1 and afro_line.count("⬜") == 9, afro_line
    assert pop_line.count("🟩") + pop_line.count("⬜") == 10
    assert "Songs explored: *2*" in text, text
    assert "Quiz: *2/9* (22%)" in text, text
    assert "Rnb" not in text, "raw key leaked into card"
    print("  blend label, 10-block bars (3 vs 1), distinct songs, quiz 2/9 (22%)")


def test_card_empty_state():
    _reset()
    text = _card_text(5513)
    assert "growing" in text, text
    print("  fresh user -> growing nudge, no crash")


def test_card_quiz_never_played():
    _reset()
    u = 5514
    _tagged(u, "pop", 2)
    text = _card_text(u)
    assert "no games yet" in text, text
    print("  no quiz history -> 'no games yet' (no 0/0)")


def test_card_remainder_line():
    _reset()
    u = 5515
    # 5 genres -> top-3 shown, tail named on its own line
    _tagged(u, "pop", 34)
    _tagged(u, "rnb", 27)
    _tagged(u, "afrobeats", 16)
    _tagged(u, "hiphop", 15)
    _tagged(u, "country", 8)
    text = _card_text(u)
    assert "_…plus 23% across 2 more genres (Hip-Hop, Country)_" in text, text
    assert "Rnb" not in text and "Hiphop" not in text, text
    print("  tail line: plus 23% across 2 more genres (Hip-Hop, Country)")


def test_card_no_remainder_line():
    _reset()
    u = 5516
    _tagged(u, "pop", 2)
    _tagged(u, "rnb", 1)
    text = _card_text(u)
    assert "more genre" not in text, text
    print("  <=3 genres -> no tail line")


# ── 8. largest-remainder: percentages always sum to exactly 100 ──────────

def test_largest_remainder_sums_100():
    _reset()
    u = 5517
    # the reporter's real counts: naive rounding sums to 101
    for g, n in [("pop", 38), ("rnb", 31), ("afrobeats", 18),
                 ("hiphop", 11), ("country", 9), ("electronic", 2),
                 ("rock", 2), ("latin", 1), ("rap", 1)]:
        _tagged(u, g, n)
    ms = f.get_music_stats(u)
    top = dict(ms["top"])
    assert sum(top.values()) == 100, ms["top"]
    # country (.96) outranks pop (.63) for the leftover point
    assert top["pop"] == 33 and top["country"] == 8, ms["top"]
    assert top["rnb"] == 27 and top["afrobeats"] == 16, ms["top"]
    print("  real-world 101-case -> exactly 100 (pop 33, country 8)")


def test_largest_remainder_three_way_tie():
    _reset()
    u = 5518
    for g in ["pop", "rnb", "afrobeats"]:
        _tagged(u, g, 1)
    ms = f.get_music_stats(u)
    pcts = [p for _, p in ms["top"]]
    assert sum(pcts) == 100, pcts
    assert sorted(pcts, reverse=True) == [34, 33, 33], pcts
    print("  1/1/1 -> 34/33/33, sums to exactly 100")


# ── 7. _song_pairs helper ────────────────────────────────────────────────

def test_song_pairs():
    assert h._song_pairs([{"artist": "A", "name": "T"}]) == [("A", "T")]
    assert h._song_pairs([{"artist": "A", "song": "T"}],
                         title_key="song") == [("A", "T")]
    assert h._song_pairs(None) == []
    assert h._song_pairs([None, "x", {}]) == []
    assert h._song_pairs([{"artist": "A"}]) == [("A", None)]
    print("  _song_pairs: key variants, junk skipped, never raises")


# ── 8. Explorer badge: awarded on DISTINCT songs, not taps ─────────────
# Badge desc: "Discovered 50 songs". auto_award_from_stats must use
# songs_explored (distinct served songs), not total interactions.

def _serve_distinct(uid, n, start=0):
    for i in range(start, start + n):
        f.log_interaction(uid, "recommend", genre="pop",
                          songs=[(f"Artist{i}", f"Song{i}")])


def test_explorer_desc_matches_logic():
    # The honesty contract: description says "Discovered 50 songs".
    assert f.BADGES["explorer"]["desc"] == "Discovered 50 songs"
    print('  explorer desc: "Discovered 50 songs"')


def test_explorer_awarded_on_50_distinct_songs():
    _reset()
    u = 55601
    _serve_distinct(u, 50)
    ms = f.get_music_stats(u)
    assert ms["songs_explored"] == 50, ms
    newly = f.auto_award_from_stats(u)
    assert newly == ["explorer"], newly   # no other badge should fire here
    # Second call: already awarded, nothing new.
    assert f.auto_award_from_stats(u) == []
    print("  50 distinct songs -> explorer awarded once, then idempotent")


def test_explorer_not_awarded_on_repeat_taps():
    _reset()
    u = 55602
    # 60 interaction taps but only 5 DISTINCT songs — old code awarded on
    # total >= 50; honest code must not.
    for i in range(60):
        f.log_interaction(u, "recommend", genre="pop",
                          songs=[("Tyla", f"Track{i % 5}")])
    ms = f.get_music_stats(u)
    assert ms["total"] == 60 and ms["songs_explored"] == 5, ms
    newly = f.auto_award_from_stats(u)
    assert "explorer" not in newly, newly
    assert f.get_user_badges(u)["earned"] == []
    print("  60 taps / 5 distinct songs -> explorer NOT awarded (regression)")


def test_explorer_boundary():
    _reset()
    u = 55603
    _serve_distinct(u, 49)
    assert "explorer" not in f.auto_award_from_stats(u)
    _serve_distinct(u, 1, start=49)
    assert f.get_music_stats(u)["songs_explored"] == 50
    assert "explorer" in f.auto_award_from_stats(u)
    print("  49 distinct -> no award; 50th distinct -> awarded")


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
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
        print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
