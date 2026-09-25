"""Round 46: /extend mood filtering — no high-energy titles in soft moods.

A song called "Dance"/"Party"/"Club" wears the artist's own energy label.
For sad/relaxed/focus, /extend now rejects pool + live candidates whose
titles carry an unambiguous hype marker, unless a soft qualifier is present
("Slow Dancing in the Dark" is spared).  Curated genre pools were already
clean; the leak came from RANDOM_SONGS_POOL (Whitney Houston "I Wanna
Dance with Somebody" in a Relaxed set).
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


f = d._title_fits_soft_mood

# ── unit: helper ───────────────────────────────────────────────────────
check("dance rejected for relaxed", f("I Wanna Dance with Somebody", "relaxed") is False)
check("dance rejected for sad", f("Dancing Queen", "sad") is False)
check("dance rejected for focus", f("One Dance", "focus") is False)
check("party rejected for relaxed", f("Party Rock Anthem", "relaxed") is False)
check("club rejected for sad", f("Club Can't Handle Me", "sad") is False)
check("twerk rejected for relaxed", f("Twerk It", "relaxed") is False)
check("dance ALLOWED for happy", f("I Wanna Dance with Somebody", "happy") is True)
check("dance ALLOWED for party", f("Dancing Queen", "party") is True)
check("dance ALLOWED for energetic", f("One Dance", "energetic") is True)
check("soft qualifier SPARES slow dancing",
      f("Slow Dancing in the Dark", "relaxed") is True)
check("soft qualifier SPARES stripped",
      f("Dance With Me (Stripped)", "sad") is True)
check("plain title fine for relaxed", f("Snooze", "relaxed") is True)
check("plain title fine for sad", f("Someone Like You", "sad") is True)
check("case-insensitive", f("DANCE WITH SOMEBODY", "relaxed") is False)
check("word boundary: 'Dancer' not flagged",
      f("Maneater Dancer", "relaxed") is True)
check("never raises on None", f(None, "relaxed") is True)
check("never raises on int", f(123, "relaxed") is True)
check("never raises on bad mood", f("Snooze", None) is True)

# ── integration: the user's exact scenario ────────────────────────────
# SZA / Weeknd / Daniel Caesar -> rnb + relaxed.  Run many times because
# the pool order is shuffled; Whitney must NEVER appear.
inputs = [{"artist": "SZA", "song": "Snooze"},
          {"artist": "The Weeknd", "song": "Blinding Lights"},
          {"artist": "Daniel Caesar", "song": "Get You"}]
leaked = 0
for _ in range(40):
    recs = d.get_extend_recs(inputs, 5)
    if any("dance with somebody" in r["name"].lower() for r in recs):
        leaked += 1
check("user scenario: no hype leak in 40 runs", leaked == 0, f"leaked {leaked}x")

recs = d.get_extend_recs(inputs, 5)
check("user scenario: still 5 recs", len(recs) == 5, str(recs))
check("user scenario: vibe still rnb",
      d.blend_vibe(inputs)["genre"] == "rnb")

# ── integration: live top-up gated too ────────────────────────────────
_old = d._similar_quick
try:
    d._similar_quick = lambda *a, **k: [
        {"artist": "ABBA", "name": "Dancing Queen", "reason": ""},
        {"artist": "Adele", "name": "Easy On Me", "reason": ""}]
    recs = d.get_extend_recs(
        [{"artist": "Adele", "song": "Someone Like You"},
         {"artist": "Sam Smith", "song": "Stay With Me"},
         {"artist": "Billie Eilish", "song": "Ocean Eyes"}], 5)
    names = [r["name"].lower() for r in recs]
    check("live top-up: hype song blocked for sad",
          "dancing queen" not in names, str(names))
finally:
    d._similar_quick = _old

# ── no over-filtering: happy mood still serves hype ──────────────────
check("happy mood keeps hype titles",
      f("Dancing Queen", "happy") is True and
      f("Party Rock Anthem", "happy") is True)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
