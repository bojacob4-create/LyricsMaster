"""Round 47: /about honesty + truthful reasons + theme synonyms.

Fix A: zero-signal themes (no keyword/genre/mood hit anywhere) return []
so the caller shows the honest "couldn't find songs for that theme"
message instead of five alphabetical songs with a false "Matches" claim
(the /about gym screenshot: a-ha, ABBA, ADELA...).
Fix B: each song's reason states what THAT song actually matched.
Fix C: _THEME_SYNONYMS expands interpret_theme keywords on both the
OpenAI and local paths (gym -> workout/exercise/pump, ...).
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


# Force the local theme fallback (no OpenAI) for deterministic tests.
_old_client = nlp._get_client
nlp._get_client = lambda: None


# ── Fix A: zero signal -> [] ──────────────────────────────────────────
check("A: 'gym' theme -> [] (no signal)",
      d.match_theme(d.interpret_theme('gym'), 5) == [])
check("A: gibberish theme -> []",
      d.match_theme(d.interpret_theme('xyzqwe'), 5) == [])
check("A: empty-ish theme -> []",
      d.match_theme(d.interpret_theme('the'), 5) == [])
recs = d.match_theme({'mood': 'relaxed', 'keywords': ['rnb'],
                      'genres': ['rnb']}, 5)
check("A: genre theme still works",
      len(recs) == 5 and all(
          d.ARTIST_GENRE_MAP.get(r['artist'].lower(), 'pop') == 'rnb'
          for r in recs),
      str([(r['artist'], r['song']) for r in recs]))
recs = d.match_theme({'mood': 'relaxed', 'keywords': ['summer'],
                      'genres': []}, 5)
check("A: real keyword theme still works",
      len(recs) == 5 and 'summer' in recs[0]['song'].lower(),
      str([(r['artist'], r['song']) for r in recs]))

# ── Fix B: per-song truthful reasons ──────────────────────────────────
recs = d.match_theme({'mood': 'relaxed',
                      'keywords': ['summer', 'night'], 'genres': []}, 5)
ok = True
for r in recs:
    rsn = r.get('reason', '')
    if rsn.startswith("Matches '"):
        quoted = rsn[len("Matches '"):-1].split(' & ')
        blob = (r['song'] + ' ' + r['artist']).lower()
        if not any(q in blob for q in quoted):
            ok = False
    elif not rsn:
        ok = False
check("B: every reason truthful for its song", ok,
      str([(r['artist'], r['song'], r['reason']) for r in recs]))
check("B: no shared false template",
      not any("Matches 'gym': gym" in r.get('reason', '') for r in recs))
recs = d.match_theme({'mood': 'relaxed', 'keywords': ['rnb'],
                      'genres': ['rnb']}, 5)
check("B: genre-only reason names the genre",
      all('pick' in r.get('reason', '').lower() for r in recs),
      str([r['reason'] for r in recs]))

# ── Fix C: synonym expansion ──────────────────────────────────────────
t = d.interpret_theme('gym')
check("C: 'gym' expands to workout/exercise",
      'workout' in t['keywords'] and 'exercise' in t['keywords'],
      str(t))
check("C: mood still energetic for gym", t['mood'] == 'energetic', str(t))
t = d.interpret_theme('heartbreak')
check("C: 'heartbreak' expands",
      any(w in t['keywords'] for w in ('goodbye', 'tears', 'heartbroken')),
      str(t))
t = d.interpret_theme('summer nights')
check("C: keywords capped at 6", len(t['keywords']) <= 6, str(t))
check("C: no duplicate keywords",
      len(t['keywords']) == len(set(t['keywords'])), str(t))
check("C: expansion never raises",
      d._expand_theme_keywords(None) == [] and
      d._expand_theme_keywords(['gym', 'gym']) == ['gym', 'workout',
                                                   'exercise', 'pump'])
check("C: unknown words pass through",
      d._expand_theme_keywords(['xyzqwe']) == ['xyzqwe'])

# synonyms actually help a real theme score
recs = d.match_theme({'mood': 'relaxed',
                      'keywords': d._expand_theme_keywords(['summer']),
                      'genres': []}, 5)
check("C: expanded 'summer' still serves", len(recs) == 5)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
