"""Comprehensive behavior test for Lyrics Master bot (service level).

Covers: lyrics, similar songs, ambiguous recommend, analysis, translate,
YouTube, artist info, random diversity, quiz flow, NLP intent.
Run: ../venv/bin/python test_comprehensive.py
"""
import os, sys, time, random

# Match run_bot.sh env sanitization (bracketed IPv6 in NO_PROXY breaks httpx)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env without printing values
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
for _line in open(_env_path):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

PASS, FAIL = "PASS", "FAIL"
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail else ""))

def timed(fn, *a, **k):
    t = time.time()
    out = fn(*a, **k)
    return out, round(time.time() - t, 1)

print("=" * 60)
print("LYRICS MASTER — comprehensive behavior test")
print("=" * 60)

# ── 1. Lyrics lookup ──────────────────────────────────────────────
from services.lyrics_service import get_song_lyrics
lyrics, dt = timed(get_song_lyrics, "Tyla", "Water")
check("lyrics: Tyla - Water found", bool(lyrics and len(lyrics) > 200), f"{len(lyrics or '')} chars, {dt}s")
lyrics_none, _ = timed(get_song_lyrics, "Xyzq", "NonexistentSong123")
check("lyrics: gibberish returns nothing", not lyrics_none)

# ── 2. Similar songs — quality + latency ───────────────────────────
from services.recommendation_service import get_similar_songs
for artist, song in [("Ayra Starr", "Rush"), ("Tyla", "Water"), ("Queen", "Bohemian Rhapsody")]:
    recs, dt = timed(get_similar_songs, artist, song, "romantic")
    arts = [r["artist"] for r in recs]
    ok = len(recs) == 5 and len(set(a.lower() for a in arts)) == 5
    reasons = all(r.get("reason") for r in recs)
    check(f"similar: {artist} - {song} → 5 unique artists w/ reasons",
          ok and reasons, f"{dt}s: " + ", ".join(f"{r['artist']} - {r['name']}" for r in recs[:5]))

# ── 3. Ambiguous /recommend ('rush') ───────────────────────────────
from services.nlp_router import search_song_candidates, is_dominant_match
cands = search_song_candidates("rush")
check("recommend: 'rush' has multiple candidates (ambiguous path)",
      len(cands) > 1 and not is_dominant_match(cands),
      f"{len(cands)} candidates, top: {cands[0]['artist']} - {cands[0]['song']}" if cands else "none")

# ── 4. Analysis: stats / mood / themes ────────────────────────────
from utils import get_song_statistics, format_statistics, detect_song_mood, detect_themes, get_detailed_song_analysis
sample = ("Hello darkness my old friend\nI've come to talk with you again\n"
          "Because a vision softly creeping\nLeft its seeds while I was sleeping\n" * 4)
stats = get_song_statistics(sample)
check("analysis: word count sane", stats.get("total_words", 0) > 30, f"words={stats.get('total_words')}")
check("analysis: themes detected", bool(detect_themes(sample)))
check("analysis: mood detected", detect_song_mood(sample) in
      ("happy", "sad", "romantic", "energetic", "relaxed"))
det = get_detailed_song_analysis(sample)
check("analysis: detailed keys present",
      all(k in det for k in ("mood", "themes", "rhyme_analysis")), f"keys={sorted(det.keys())[:6]}")
acc = "Beyoncé café naïve"
stats_acc = get_song_statistics(acc)
check("analysis: unicode words counted", stats_acc.get("total_words", 0) >= 3,
      f"words={stats_acc.get('total_words')}")

# ── 5. Translate ──────────────────────────────────────────────────
from services.translator_service import translate_to_arabic
tr, dt = timed(translate_to_arabic, "Hello, how are you my friend")
check("translate: en→ar works", bool(tr and tr != "Hello, how are you my friend"), f"{dt}s → {str(tr)[:40]}")

# ── 6. YouTube link ───────────────────────────────────────────────
from services.youtube_service import get_youtube_link
yt, dt = timed(get_youtube_link, "Tyla", "Water")
check("youtube: link found", bool(yt and "youtu" in yt), f"{dt}s")

# ── 7. Artist info ────────────────────────────────────────────────
from services.artist_service import get_artist_info, get_random_song, RANDOM_SONGS_POOL
info = get_artist_info("Tyla")
check("artist: Tyla info found", bool(info and info.get("genre")), f"genre={info.get('genre') if info else '?'}")

# ── 8. Random pool diversity ──────────────────────────────────────
picks = [f"{p['artist']} - {p['song']}" for p in (get_random_song() for _ in range(60))]
uniq = len(set(picks))
check("random: 60 picks diversity", uniq >= 25, f"{uniq}/60 unique (pool={len(RANDOM_SONGS_POOL)})")

# ── 9. Quiz flow ──────────────────────────────────────────────────
from services import quiz_service
pool = quiz_service.get_quiz_songs()
check("quiz: song pool size", len(pool) >= 40, f"{len(pool)} songs")
q = quiz_service.get_quiz_question()
ok_q = bool(q and q.get("snippet") and len(q.get("options", [])) == 4
            and 0 <= q.get("answer_index", -1) < 4)
check("quiz: question valid (snippet + 4 options + answer_index)", ok_q,
      f"type={q.get('qtype') if q else '?'}" if ok_q else "")
qd = quiz_service.start_quiz(999001)
check("quiz: start_quiz works", bool(qd and qd["state"] == "active"))
if qd:
    cur = qd["current_question"]
    letter = "ABCD"[cur["answer_index"]]
    is_ok, fb = quiz_service.check_answer(999001, letter)
    check("quiz: correct letter answer accepted", is_ok)
    nxt = quiz_service.active_quizzes[999001]["current_question"]
    check("quiz: next question is a different song",
          (nxt["artist"], nxt["song"]) != (cur["artist"], cur["song"]))
    is_ok2, fb2 = quiz_service.check_answer(999001, "ZZZ_WRONG")
    check("quiz: wrong answer rejected", not is_ok2)
    quiz_service.end_quiz(999001)

# ── 10. NLP with live key ─────────────────────────────────────────
from services.nlp_router import parse_intent
res, dt = timed(parse_intent, "find lyrics for water by tyla")
check("nlp: free-form intent parsed", res.get("intent") in ("lyrics", "song"),
      f"{dt}s intent={res.get('intent')} artist={res.get('artist')} song={res.get('song')}")

print("=" * 60)
n_pass = sum(1 for _, ok, _ in results if ok)
print(f"RESULT: {n_pass}/{len(results)} passed")
sys.exit(0 if n_pass == len(results) else 1)
