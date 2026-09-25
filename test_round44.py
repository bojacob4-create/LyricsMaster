"""Round 44: /extend dash-less lines + fuzzy input exclusion.

Fix 1: parse_extend_lines accepts natural dash-less lines ("Tyla water")
via the bot-wide song-query parser, gated on known artists (picks the
right split for typos, rejects prose).
Fix 2: get_extend_recs excludes input songs fuzzily, so a typo'd input
("Rema - clam down") can't be recommended back ("Rema - Calm Down").
"""
import sys
sys.path.insert(0, '.')

from services import discovery_service as d

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} :: {detail}")


# ── Fix 1: dash-less lines ───────────────────────────────────────────────
p = d.parse_extend_lines("Tyla water\nRema calm down\nAyra starr rush")
check("dashless: 3 songs parsed", len(p) == 3, str(p))
check("dashless: Tyla split right",
      p and p[0] == {"artist": "Tyla", "song": "water"}, str(p))
check("dashless: Ayra Starr split right",
      len(p) == 3 and p[2] == {"artist": "Ayra starr", "song": "rush"}, str(p))

# Known-artist gate picks the right split on typos ("Rema clam down").
p = d.parse_extend_lines("Rema clam down")
check("dashless: typo line -> artist Rema",
      len(p) == 1 and p[0] == {"artist": "Rema", "song": "clam down"}, str(p))

# Prose lines are still rejected; dash format untouched (incl. en dash).
p = d.parse_extend_lines("Tyla - Water\n  junk line no dash  \nAyra Starr \u2013 Rush")
check("mixed: prose skipped, dashes kept",
      len(p) == 2 and p[0] == {"artist": "Tyla", "song": "Water"}
      and p[1] == {"artist": "Ayra Starr", "song": "Rush"}, str(p))

# Old strict contract for dashed lines is unchanged.
p = d.parse_extend_lines("Tyla - Water\nRema - Calm Down")
check("dash format unchanged",
      p == [{"artist": "Tyla", "song": "Water"},
            {"artist": "Rema", "song": "Calm Down"}], str(p))

# ── Fix 2: fuzzy input exclusion ─────────────────────────────────────────
check("fuzzy: exact match excluded",
      d._song_keys_match("rema", "calm down", "rema", "calm down"))
check("fuzzy: typo match caught",
      d._song_keys_match("rema", "clam down", "rema", "calm down"))
check("fuzzy: distinct songs not matched",
      not d._song_keys_match("davido", "fall", "davido", "peru"))
check("fuzzy: different artist not matched",
      not d._song_keys_match("rema", "calm down", "tyla", "calm down"))
check("fuzzy: case-insensitive",
      d._is_excluded_song("Rema", "CALM DOWN", {("rema", "calm down")}))

# End-to-end: the user's exact wild case — typo'd input must not come back.
_old_sim = d.get_similar_songs
d.get_similar_songs = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
try:
    recs = d.get_extend_recs(
        [{"artist": "Rema", "song": "clam down"},
         {"artist": "Tyla", "song": "water"},
         {"artist": "Ayra Starr", "song": "rush"}], 5)
    bad = [r for r in recs
           if r["artist"].lower() == "rema" and "calm down" in r["name"].lower()]
    check("e2e: typo'd own song not recommended", not bad, str(recs))
    check("e2e: still returns recommendations", len(recs) >= 1, str(recs))
    # Exact input exclusion still works.
    recs2 = d.get_extend_recs(
        [{"artist": "Tyla", "song": "Water"},
         {"artist": "Rema", "song": "Calm Down"},
         {"artist": "Ayra Starr", "song": "Rush"}], 5)
    bad2 = [r for r in recs2
            if (r["artist"].lower(), r["name"].lower())
            in {("tyla", "water"), ("rema", "calm down"), ("ayra starr", "rush")}]
    check("e2e: exact inputs still excluded", not bad2, str(recs2))
finally:
    d.get_similar_songs = _old_sim

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
