"""Round 48: /about live path — LLM theme songs verified via iTunes.

- _itunes_match: the hallucination guard (Britney/Work B**ch vs Hold Me
  Closer must NOT verify).
- _validate_theme_songs: strict parsing of the LLM's JSON.
- get_theme_songs_live: verified songs with "why" reasons, cached.
- local_theme_topup: only real-signal local songs, never filler.
- Fallbacks: no OpenAI client -> local; live empty + local empty -> [].
"""
import sys
sys.path.insert(0, '.')

from services import discovery_service as d
from services import nlp_router as nlp

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} :: {detail}")


# ── identity matcher ────────────────────────────────────────────────
check("match: feat credit both sides",
      d._itunes_match("David Guetta feat. Sia", "Titanium",
                      "David Guetta", "Titanium (feat. Sia)"))
check("match: punctuation-insensitive",
      d._itunes_match("Kendrick Lamar", "HUMBLE.",
                      "Kendrick Lamar", "HUMBLE."))
check("match: case-insensitive",
      d._itunes_match("eminem", "lose yourself",
                      "Eminem", "Lose Yourself"))
check("no-match: wrong song same artist words (hallucination guard)",
      not d._itunes_match("Britney Spears", "Work B**ch",
                          "Elton John & Britney Spears", "Hold Me Closer"))
check("no-match: different artist",
      not d._itunes_match("Adele", "Hello",
                          "Lionel Richie", "Hello"))
check("no-match: empty inputs",
      not d._itunes_match("", "Hello", "Adele", "Hello"))
check("norm: strips parens/feat/punct",
      d._norm_search_text("Titanium (feat. Sia)") == "titanium"
      and d._norm_search_text("X Gon' Give It to Ya") == "x gon give it to ya")

# ── LLM response validation ─────────────────────────────────────────
good = {"songs": [
    {"artist": "Eminem", "title": "Lose Yourself", "why": "Relentless drive"},
    {"artist": "Eminem", "title": "Lose Yourself", "why": "dup"},
    {"artist": "S", "title": "T"},
    {"artist": "", "title": "Nope"},
    "junk",
    {"artist": "A" * 90, "title": "Too long"},
]}
v = d._validate_theme_songs(good)
check("validate: keeps good, drops dupes/junk",
      len(v) == 2 and v[0]["artist"] == "Eminem"
      and v[0]["why"] == "Relentless drive", str(v))
check("validate: garbage in -> []",
      d._validate_theme_songs(None) == []
      and d._validate_theme_songs({"songs": "nope"}) == []
      and d._validate_theme_songs({"nope": []}) == [])

# ── iTunes verification (stubbed search) ────────────────────────────
_real_search = d._itunes_search
d._itunes_search = lambda term: [
    {"artistName": "Elton John & Britney Spears",
     "trackName": "Hold Me Closer"},
    {"artistName": "Britney Spears", "trackName": "Work Bitch"},
] if "Britney" in term else [
    {"artistName": "Eminem", "trackName": "Lose Yourself (Karaoke)"},
    {"artistName": "Eminem", "trackName": "Lose Yourself"},
]
try:
    check("verify: skips karaoke, takes the real one",
          d._verify_theme_song("Eminem", "Lose Yourself") ==
          {"artist": "Eminem", "song": "Lose Yourself"})
    check("verify: hallucinated title rejected",
          d._verify_theme_song("Britney Spears", "Work B**ch") is None)
finally:
    d._itunes_search = _real_search

# ── live path (stubbed LLM + verifier) ──────────────────────────────
_real_llm = d._llm_theme_songs
_real_verify = d._verify_theme_song
calls = {"llm": 0}
llm_songs = [
    {"artist": "Eminem", "title": "Lose Yourself", "why": "Relentless drive"},
    {"artist": "Survivor", "title": "Eye of the Tiger",
     "why": "Training montage classic"},
    {"artist": "Fake", "title": "No Such Song", "why": "hallucinated"},
]


def fake_llm(theme, query):
    calls["llm"] += 1
    return [dict(s) for s in llm_songs]


def fake_verify(a, t):
    if a == "Fake":
        return None
    return {"artist": a, "song": t}


d._llm_theme_songs = fake_llm
d._verify_theme_song = fake_verify
d._THEME_SONGS_CACHE.clear()
try:
    theme = {"mood": "energetic", "keywords": ["gym", "workout"],
             "genres": []}
    songs = d.get_theme_songs_live(theme, "gym", 5)
    check("live: verified songs with why-reasons",
          len(songs) == 2
          and songs[0]["reason"] == "Relentless drive"
          and songs[1]["song"] == "Eye of the Tiger",
          str(songs))
    check("live: cached — no second LLM call",
          d.get_theme_songs_live(theme, "gym", 5) == songs
          and calls["llm"] == 1, str(calls))
    check("live: empty query -> []",
          d.get_theme_songs_live(theme, "   ", 5) == [])
finally:
    d._llm_theme_songs = _real_llm
    d._verify_theme_song = _real_verify
    d._THEME_SONGS_CACHE.clear()

# ── no OpenAI client -> [] (local fallback owns the answer) ─────────
_old_client = nlp._get_client
nlp._get_client = lambda: None
try:
    check("live: no client -> []",
          d._llm_theme_songs({"mood": "energetic"}, "gym") == [])
finally:
    nlp._get_client = _old_client

# ── local top-up: real signal only ──────────────────────────────────
_old_client = nlp._get_client
nlp._get_client = lambda: None
try:
    theme = d.interpret_theme("summer nights")
    top = d.local_theme_topup(theme, set(), 3)
    check("topup: real-signal songs only",
          1 <= len(top) <= 3
          and all("Matches" in s["reason"] for s in top),
          str(top))
    seen = {(s["artist"].lower(), s["song"].lower()) for s in top}
    seen_before = set(seen)  # local_theme_topup mutates the passed set
    top2 = d.local_theme_topup(theme, seen, 3)
    check("topup: excludes already-served",
          all((s["artist"].lower(), s["song"].lower()) not in seen_before
              for s in top2))
    check("topup: zero-signal theme -> []",
          d.local_theme_topup(d.interpret_theme("xyzqwe"), set(), 3) == [])
finally:
    nlp._get_client = _old_client

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
