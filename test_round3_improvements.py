"""Tests for the round-3 improvements: random, similar-fresh, quiz v2."""
import os, sys, time

os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
for _l in open(_env):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        _k, _v = _l.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

results = []
def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

print("=" * 60)
print("ROUND-3 improvement tests")
print("=" * 60)

# ── Random: bigger pool, per-user no-repeat, genre pick ──────────
from services.artist_service import get_random_song, RANDOM_SONGS_POOL, _recent_random_picks
check("random pool expanded", len(RANDOM_SONGS_POOL) >= 100, f"{len(RANDOM_SONGS_POOL)} songs")

picks = [get_random_song(user_id=777001) for _ in range(60)]
uniq = len(set(f"{p['artist']} - {p['song']}" for p in picks))
check("random: 60 picks diverse", uniq >= 40, f"{uniq}/60 unique")

# no repeat within any sliding window of 12
names = [f"{p['artist']} - {p['song']}".lower() for p in picks]
repeat = any(len(set(names[i:i+12])) < 12 for i in range(len(names) - 12))
check("random: no repeat within last 12 picks", not repeat)

g = get_random_song(user_id=777002, genre="pop")
check("random: genre pick works", bool(g.get("artist") and g.get("song")),
      f"{g['artist']} - {g['song']}")
g2 = get_random_song(user_id=777002, genre="notagenre")
check("random: bad genre falls back to pool", bool(g2.get("artist")))

# ── Similar: fresh path excludes shown artists ──────────────────
from services.recommendation_service import get_similar_songs, get_similar_songs_fresh
base, dt = time.time(), 0
t0 = time.time()
recs = get_similar_songs("Ayra Starr", "Rush", "romantic")
dt = round(time.time() - t0, 1)
shown = [r["artist"] for r in recs]
check("similar: blended 5 results", len(recs) == 5 and len(set(a.lower() for a in shown)) == 5,
      f"{dt}s: " + ", ".join(f"{r['artist']} - {r['name']}" for r in recs))
check("similar: all have reasons", all(r.get("reason") for r in recs))

t0 = time.time()
fresh = get_similar_songs_fresh("Ayra Starr", "Rush", "romantic", exclude_artists=shown)
dt2 = round(time.time() - t0, 1)
fresh_artists = [r["artist"].lower() for r in fresh]
overlap = set(fresh_artists) & set(a.lower() for a in shown)
check("similar-fresh: 5 new picks, no overlap with shown",
      len(fresh) == 5 and not overlap, f"{dt2}s: " + ", ".join(fresh_artists))

# ── Quiz v2: 3 question types, hard mode, best scores ────────────
from services import quiz_service as qs
check("quiz pool expanded", len(qs.get_quiz_songs()) >= 100,
      f"{len(qs.get_quiz_songs())} songs")

seen_types = set()
ok_all = True
# Validate structure on the first 10, but draw up to 30 for type coverage:
# requiring all 3 types in exactly 10 random draws flakes ~5% of the time.
for i in range(30):
    q = qs.get_quiz_question(exclude_songs=[], hard=(i % 2 == 0))
    if not q:
        ok_all = False
        break
    seen_types.add(q["qtype"])
    if i >= 10:
        continue
    opts = q["options"]
    ai = q["answer_index"]
    if not (0 <= ai < len(opts) == 4):
        ok_all = False
    if q["qtype"] == "complete_lyric":
        if not all("line" in o for o in opts):
            ok_all = False
        if len(set(o["line"] for o in opts)) != 4:
            ok_all = False
    if q.get("hard") and q["qtype"] in ("guess_song", "guess_artist"):
        if len(q["snippet"].split("\n")) != 2:
            ok_all = False
check("quiz: 10 questions valid across types", ok_all and len(seen_types) == 3,
      f"types seen: {sorted(seen_types)}")

# full game flow with correct answers via answer_index
qd = qs.start_quiz(888001)
flow_ok = bool(qd)
types_played = set()
for _ in range(6):
    if not qd or qs.active_quizzes.get(888001, {}).get("state") != "active":
        break
    cur = qs.active_quizzes[888001]["current_question"]
    types_played.add(cur["qtype"])
    letter = "ABCD"[cur["answer_index"]]
    ok, fb = qs.check_answer(888001, letter)
    if not ok:
        flow_ok = False
        break
check("quiz: 6 correct answers in a row accepted", flow_ok,
      f"types played: {sorted(types_played)}")
st = qs.active_quizzes.get(888001)
check("quiz: streak tracked", bool(st and st["streak"] == 6 and st["best_streak"] == 6),
      f"streak={st['streak'] if st else '?'}" if st else "no quiz")
hard_q = st["current_question"] if st else None
check("quiz: hard mode active at streak>=4", bool(hard_q and hard_q.get("hard")))
end_msg = qs.end_quiz(888001)
check("quiz: end records personal best", "Personal best" in end_msg)
pb = qs.get_personal_best(888001)
check("quiz: personal best persisted", bool(pb and pb.get("best_streak") == 6),
      str(pb))
# wrong free-text answer
qs.start_quiz(888002)
cur = qs.active_quizzes[888002]["current_question"]
ok, _ = qs.check_answer(888002, "definitely not the answer xyz")
check("quiz: wrong free-text rejected", not ok)
qs.end_quiz(888002)

print("=" * 60)
n = sum(results)
print(f"RESULT: {n}/{len(results)} passed")
sys.exit(0 if n == len(results) else 1)
