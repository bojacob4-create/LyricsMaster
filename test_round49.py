#!/usr/bin/env python3
"""Round 49: /throwback goes big — Billboard-mined pool, no-repeat memory,
honest decade handling. Zero OpenAI, zero network, zero cost at runtime."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")

import services.discovery_service as d  # noqa: E402
from services.throwback_pool import THROWBACK_MINED  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


# ── mined pool integrity ─────────────────────────────────────────────
check("mined: 4 decades",
      set(THROWBACK_MINED.keys()) == {"80s", "90s", "2000s", "2010s"})
check("mined: big pools (>=400 each)",
      all(len(v) >= 400 for v in THROWBACK_MINED.values()),
      str({k: len(v) for k, v in THROWBACK_MINED.items()}))
check("mined: entries have artist/song/year/rank",
      all(all(e.get("artist") and e.get("song") and e.get("year")
              and e.get("rank") for e in v)
          for v in THROWBACK_MINED.values()))


def _decade_of(year):
    return ("80s" if year < 1990 else "90s" if year < 2000
            else "2000s" if year < 2010 else "2010s")


check("mined: every song's year matches its decade",
      all(_decade_of(e["year"]) == dec
          for dec, v in THROWBACK_MINED.items() for e in v))

# ── curated pool untouched ───────────────────────────────────────────
check("curated: 4 decades x 16 with facts",
      set(d.DECADE_POOLS.keys()) == {"80s", "90s", "2000s", "2010s"}
      and all(len(v) == 16 and all(s.get("fact") for s in v)
              for v in d.DECADE_POOLS.values()))

# ── get_throwback shape ──────────────────────────────────────────────
d._THROWBACK_SEEN.clear()
tb = d.get_throwback("90s", 5, user_id=7)
check("throwback: 5 picks with artist/song/note",
      len(tb) == 5 and all(s.get("artist") and s.get("song") and s.get("note")
                           for s in tb),
      str(tb))
facts = [s for s in tb if s["note"].startswith("\U0001f4a1")]
charts = [s for s in tb if s["note"].startswith("\U0001f4ca")]
check("throwback: 2 trivia-fact picks + 3 chart-note picks",
      len(facts) == 2 and len(charts) == 3,
      str([s["note"][:40] for s in tb]))
import re as _re
check("throwback: chart notes carry real year+rank",
      all(_re.search(r"#\d+ on the (19|20)\d{2} year-end Hot 100", s["note"])
          for s in charts))

# ── no-repeat memory ─────────────────────────────────────────────────
d._THROWBACK_SEEN.clear()
seen_curated, seen_mined = set(), set()
dup = False
for _ in range(8):  # 8 x 2 curated = full 16-song curated pool
    for s in d.get_throwback("80s", 5, user_id=42):
        k = (s["artist"].lower(), s["song"].lower())
        if s["note"].startswith("\U0001f4a1"):
            if k in seen_curated:
                dup = True
            seen_curated.add(k)
        else:
            if k in seen_mined:
                dup = True
            seen_mined.add(k)
check("throwback: no repeats within a pool cycle",
      not dup and len(seen_curated) == 16,
      f"curated={len(seen_curated)} mined={len(seen_mined)}")
ninth = d.get_throwback("80s", 5, user_id=42)
check("throwback: pool cycles cleanly after exhaustion",
      len(ninth) == 5)

# different users don't share repeat memory
d._THROWBACK_SEEN.clear()
a = d.get_throwback("90s", 5, user_id=1)
b = d.get_throwback("90s", 5, user_id=2)
check("throwback: repeat memory is per-user",
      (1, "90s", "curated") in d._THROWBACK_SEEN
      and (2, "90s", "curated") in d._THROWBACK_SEEN)

# ── strict decade normalization ─────────────────────────────────────
check("strict: '70s' -> None", d.normalize_decade_strict("70s") is None)
check("strict: 'junk' -> None", d.normalize_decade_strict("junk") is None)
check("strict: '2021' -> None", d.normalize_decade_strict("2021") is None)
check("strict: '80s' -> 80s", d.normalize_decade_strict("80s") == "80s")
check("strict: '1995' -> 90s", d.normalize_decade_strict("1995") == "90s")
check("strict: 'eighties' -> 80s",
      d.normalize_decade_strict("eighties") == "80s")

# ── backward compatibility (round-4 contract) ────────────────────────
check("compat: normalize_decade('junk') still a valid decade",
      d.normalize_decade("junk") in d.DECADE_POOLS)
check("compat: get_throwback without user_id works",
      len(d.get_throwback("2000s", 5)) == 5)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
