"""Round 4 feature tests — service level, no Telegram network needed.

Covers all 10 features (mood / extend / about / throwback / newmusic /
duel / daily / emoji / mystats / badges) plus handler registration checks.
Run: ../venv/bin/python test_round4.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import services.discovery_service as d
import services.fun_service as f
import services.nlp_router as nlp

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


def _boom(*a, **k):
    raise RuntimeError("simulated API outage")


# ── 1. /mood ──────────────────────────────────────────────────────────────
check("mood: normalize 'hyped'", d.normalize_mood("hyped") == "energetic")
check("mood: normalize 'STUDY session'", d.normalize_mood("STUDY session") == "focus")
check("mood: canonical passthrough", d.normalize_mood("party") == "party")
check("mood: unknown -> None", d.normalize_mood("zzz unknown mood") is None)
check("mood: 6 pools x >=15",
      len(d.MOOD_SONG_POOLS) == 6 and all(len(v) >= 15 for v in d.MOOD_SONG_POOLS.values()))

_old_sim = d.get_similar_songs
d.get_similar_songs = _boom  # simulate Last.fm down
try:
    mix = d.get_mood_mix("energetic", 5)
    check("mood: offline mix -> 5 songs",
          len(mix) == 5 and all(s.get("artist") and s.get("name") and s.get("reason") for s in mix),
          f"got {len(mix)}")
finally:
    d.get_similar_songs = _old_sim

# ── 2. /extend ────────────────────────────────────────────────────────────
parsed = d.parse_extend_lines("Tyla - Water\nRema - Calm Down\n  junk line no dash  \nAyra Starr – Rush")
check("extend: parse 3 songs (both dash types)",
      len(parsed) == 3 and parsed[0] == {"artist": "Tyla", "song": "Water"}, str(parsed))
vibe = d.blend_vibe([{"artist": "Tyla", "song": "Water"},
                     {"artist": "Rema", "song": "Calm Down"},
                     {"artist": "Ayra Starr", "song": "Rush"}])
check("extend: vibe genre afrobeats", vibe.get("genre") == "afrobeats", str(vibe))
check("extend: vibe label", bool(vibe.get("label")))

d.get_similar_songs = _boom
try:
    recs = d.get_extend_recs(parsed, 5)
    check("extend: offline recs -> 5, no vibe-repeating reasons (round 45)",
          len(recs) == 5 and all("Fits your" not in (r.get("reason") or "")
                                 and "Matches your" not in (r.get("reason") or "")
                                 for r in recs), f"got {recs}")
    given = {(s["artist"].lower(), s["song"].lower()) for s in parsed}
    check("extend: input songs excluded",
          not any((r["artist"].lower(), r["name"].lower()) in given for r in recs))
finally:
    d.get_similar_songs = _old_sim

# ── 3. /about ─────────────────────────────────────────────────────────────
_old_client = nlp._get_client
nlp._get_client = lambda: None  # force local fallback (no OpenAI)
try:
    theme = d.interpret_theme("songs about starting over")
    check("about: theme shape",
          set(("mood", "keywords", "genres")) <= set(theme.keys()), str(theme))
    check("about: fallback keywords", len(theme.get("keywords", [])) > 0, str(theme))
finally:
    nlp._get_client = _old_client
songs = d.match_theme({"mood": "happy", "keywords": ["summer", "night"], "genres": []}, 5)
check("about: match -> 5 with reasons",
      len(songs) == 5 and all(s.get("artist") and s.get("song") and s.get("reason") for s in songs))

# ── 4. /throwback ─────────────────────────────────────────────────────────
check("throwback: 4 decades x >=15",
      set(d.DECADE_POOLS.keys()) == {"80s", "90s", "2000s", "2010s"}
      and all(len(v) >= 15 for v in d.DECADE_POOLS.values()))
check("throwback: normalize '80s'", d.normalize_decade("80s") == "80s")
check("throwback: normalize '1995'", d.normalize_decade("1995") == "90s")
check("throwback: bad input -> valid decade",
      d.normalize_decade("junk") in d.DECADE_POOLS)
tb = d.get_throwback("90s", 5)
check("throwback: 5 picks", len(tb) == 5 and all(s.get("artist") and s.get("song") for s in tb))

# ── 5. /newmusic ──────────────────────────────────────────────────────────
_old_trend = d.get_trending_songs
_old_genre = d._get_live_genre_songs
d.get_trending_songs = lambda: ([], False)   # chart down
d._get_live_genre_songs = _boom
try:
    nm, live = d.get_new_music(None, 5)
    check("newmusic: chart-down fallback -> 5, honest is_live=False",
          len(nm) == 5 and live is False, f"got {len(nm)}, live={live}")
    nm2, live2 = d.get_new_music("afrobeats", 5)
    check("newmusic: genre fallback -> 5, is_live=False",
          len(nm2) == 5 and live2 is False, f"got {len(nm2)}, live={live2}")
finally:
    d.get_trending_songs = _old_trend
    d._get_live_genre_songs = _old_genre

# ── Fun service: redirect JSON to /tmp ────────────────────────────────────
_tmp = tempfile.mkdtemp(prefix="r4_")
f.DUELS_PATH = os.path.join(_tmp, "duels.json")
f.DAILY_PATH = os.path.join(_tmp, "daily.json")
f.STATS_PATH = os.path.join(_tmp, "stats.json")
f.BADGES_PATH = os.path.join(_tmp, "badges.json")
f.QUIZ_CACHE_PATH = os.path.join(_tmp, "qcache.json")


def _stub_q(i):
    return {"qtype": "guess_song", "artist": f"A{i}", "song": f"S{i}",
            "snippet": "x", "options": [], "answer_index": 0}


# ── 6. /duel ──────────────────────────────────────────────────────────────
code = f.make_duel_code()
check("duel: code format",
      len(code) == 6 and code.isalnum() and code.isupper(), code)
stubs = [_stub_q(i) for i in range(5)]
duel = f.create_duel(111, "Ann", questions=list(stubs))
check("duel: create", duel.get("code") and len(f.get_duel_questions(duel["code"])) == 5)
check("duel: join", f.join_duel(duel["code"], 222, "Bob") is not None)
check("duel: join bad code -> None", f.join_duel("ZZZZZZ", 333, "X") is None)
# Ann: 4 correct, Bob: 2 correct
for i in range(5):
    f.record_duel_answer(duel["code"], 111, i < 4)
    f.record_duel_answer(duel["code"], 222, i < 2)
st = f.duel_standings(duel["code"])
check("duel: standings winner",
      st["winner"] == "111" and st["scores"] == {"111": 4, "222": 2}, str(st))
# Tie
duel2 = f.create_duel(111, "Ann", questions=list(stubs))
f.join_duel(duel2["code"], 222, "Bob")
for i in range(5):
    f.record_duel_answer(duel2["code"], 111, i < 3)
    f.record_duel_answer(duel2["code"], 222, i < 3)
st2 = f.duel_standings(duel2["code"])
check("duel: tie", st2["winner"] == "tie", str(st2["winner"]))
# Degraded: dead API + empty cache -> still works from cache
f.QUIZ_CACHE_PATH = os.path.join(_tmp, "qcache2.json")
_old_q = f.get_quiz_question
f.get_quiz_question = _boom
try:
    check("duel: dead API + empty cache -> [] no raise",
          f.create_duel(111, "Ann").get("questions") == [])
finally:
    f.get_quiz_question = _old_q

# ── 7. /daily ─────────────────────────────────────────────────────────────
uid = 4242
s0 = f.get_daily_status(uid, today="2026-09-24")
check("daily: fresh can_play", s0["can_play"] is True and s0["streak"] == 0)
r1 = f.record_daily_play(uid, 4, 5, today="2026-09-24")
check("daily: first play streak 1", r1["streak"] == 1 and r1["best_streak"] == 1)
check("daily: same day blocked",
      f.get_daily_status(uid, today="2026-09-24")["can_play"] is False)
r2 = f.record_daily_play(uid, 5, 5, today="2026-09-25")
check("daily: next day streak 2", r2["streak"] == 2 and r2["best_streak"] == 2)
r3 = f.record_daily_play(uid, 3, 5, today="2026-09-28")
check("daily: gap resets, best kept",
      r3["streak"] == 1 and r3["best_streak"] == 2, str(r3))
check("daily: make questions (stubbed cache ok)",
      isinstance(f.make_daily_questions(3, questions=[_stub_q(i) for i in range(3)]), list))

# ── 8. /emoji ─────────────────────────────────────────────────────────────
check("emoji: >=20 puzzles", len(f.EMOJI_PUZZLES) >= 20,
      f"got {len(f.EMOJI_PUZZLES)}")
puz = {"emojis": "💧", "artist": "Tyla", "song": "Water"}
check("emoji: accept 'Artist - Song'", f.check_emoji_guess(puz, "Tyla - Water"))
check("emoji: accept song only", f.check_emoji_guess(puz, "water"))
check("emoji: reject wrong", not f.check_emoji_guess(puz, "Adele - Hello"))

# ── 9. /mystats ───────────────────────────────────────────────────────────
u2 = 7777
f.log_interaction(u2, "random", genre="afrobeats")
f.log_interaction(u2, "random", genre="afrobeats")
f.log_interaction(u2, "recommend", genre="pop")
ms = f.get_music_stats(u2)
check("mystats: total 3", ms["total"] == 3, str(ms))
check("mystats: top genre afrobeats",
      ms["top"] and ms["top"][0][0] == "afrobeats" and ms["top"][0][1] > 50,
      str(ms["top"]))
check("mystats: label", bool(ms.get("label")), ms.get("label"))
check("mystats: percentages sane",
      sum(p for _, p in ms["top"]) <= 100)

# ── 10. /badges ───────────────────────────────────────────────────────────
u3 = 8888
check("badges: award new -> True", f.award_badge(u3, "first_quiz") is True)
check("badges: award again -> False", f.award_badge(u3, "first_quiz") is False)
check("badges: unknown id -> False", f.award_badge(u3, "nope") is False)
ub = f.get_user_badges(u3)
check("badges: earned/locked",
      ub["earned"] == ["first_quiz"] and "quiz_whiz" in ub["locked"], str(ub))
check("badges: 6 defined", len(f.BADGES) == 6)
u4 = 9999
for _ in range(10):
    f.log_interaction(u4, "quiz_correct")
new = f.auto_award_from_stats(u4)
check("badges: auto quiz_whiz", "quiz_whiz" in new, str(new))

# ── Registration checks (no network) ──────────────────────────────────────
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")) as fh:
    bot_src = fh.read()
for cmd in ["mood", "extend", "about", "throwback", "newmusic",
            "duel", "daily", "emoji", "mystats", "badges"]:
    check(f"register: /{cmd} in bot.py",
          f'CommandHandler("{cmd}"' in bot_src)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers.py")) as fh:
    h_src = fh.read()
for cmd in ["mood", "extend", "about", "throwback", "newmusic",
            "duel", "daily", "emoji", "mystats", "badges"]:
    check(f"help: /{cmd} in help text", f"/{cmd}" in h_src)

print("=" * 60)
print(f"RESULT: {PASS}/{PASS + FAIL} passed")
if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
