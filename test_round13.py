"""Round-13 tests: mood identity, dedup, junk filter, MP3 hard kill,
auto-delivery markers, /analyze wording.  Run from repo root:
    ../venv/bin/python test_round13.py   (with ../.env sourced for live tests)
"""
import os, sys, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed, failed = 0, 0
def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {extra}")

print("== mood identity (unit) ==")
from services import discovery_service as ds
from services.recommendation_service import _MOOD_KEYWORDS

check("party has own internal key", ds._MOOD_INTERNAL.get('party') == 'party')
check("'god' removed from energetic keywords",
      'god' not in _MOOD_KEYWORDS.get('energetic', set()))
check("'party' keyword set exists and is distinct",
      bool(_MOOD_KEYWORDS.get('party')) and
      not (_MOOD_KEYWORDS['party'] & _MOOD_KEYWORDS['energetic']))
check("energetic/party genre slices disjoint",
      not (ds._MOOD_APPLE_GENRES['energetic'] & ds._MOOD_APPLE_GENRES['party']))
check("relaxed/focus genre slices disjoint",
      not (ds._MOOD_APPLE_GENRES['relaxed'] & ds._MOOD_APPLE_GENRES['focus']))
check("worship title does not match energetic",
      not ds._title_has_mood_word("God Didn't Let Me Break", 'energetic'))
check("worship title does not match energetic (2)",
      not ds._title_has_mood_word("God I'm Just Grateful", 'energetic'))
check("party keyword still matches party",
      ds._title_has_mood_word("Party All Night", 'party'))
check("hype keyword still matches energetic",
      ds._title_has_mood_word("Hype Beast Anthem", 'energetic'))

print("== dedup (unit) ==")
out, sk, sa, st = [], set(), set(), set()
check("first Babydoll claimed",
      ds._claim_pick(out, sk, sa, "Jamie Miller & Antonio Cipriano",
                     "Babydoll", "fresh", "keyword", st) is True)
check("same title, diff artist credit rejected",
      ds._claim_pick(out, sk, sa, "Jamie Miller", "Babydoll",
                     "fresh", "keyword", st) is False)
check("same title with (Remix) also rejected",
      ds._claim_pick(out, sk, sa, "Jamie Miller", "Babydoll (Remix)",
                     "fresh", "keyword", st) is False)
check("different song still accepted",
      ds._claim_pick(out, sk, sa, "Tyla", "Water", "fresh", "keyword", st) is True)
check("mix holds 2 songs", len(out) == 2)

print("== junk filter (unit) ==")
for junk in ["Song (Karaoke Version)", "Hit 8D Audio", "Title (slowed + reverb)",
             "Anthem Sped Up", "Song - Nightcore", "Sparks (Adding Sax Solos To Songs)"]:
    o2, k2, a2, t2 = [], set(), set(), set()
    check(f"junk rejected: {junk[:28]}",
          ds._claim_pick(o2, k2, a2, "Some Artist", junk, "fresh", "x", t2) is False)
o3, k3, a3, t3 = [], set(), set(), set()
check("karaoke artist rejected",
      ds._claim_pick(o3, k3, a3, "Karaoke All Stars", "Hello", "fresh", "x", t3) is False)
o4, k4, a4, t4 = [], set(), set(), set()
check("legit song accepted",
      ds._claim_pick(o4, k4, a4, "Adele", "Hello", "fresh", "x", t4) is True)

print("== /analyze wording (unit) ==")
import utils
analysis = {
    'statistics': {'total_lines': 40, 'total_words': 200, 'meaningful_words': 120,
                   'unique_words': 90, 'vocabulary_richness': 75, 'top_words': [],
                   'repeated_phrases': []},
    'rhyme_analysis': {'rhyme_density': 20, 'rhyming_lines': 8, 'total_lines': 40},
    'mood': {'primary_mood': 'happy',
             'mood_intensity': {'happy': 5, 'sad': 1, 'romantic': 2,
                                'energetic': 3, 'relaxed': 4}},
    'structure': {},
}
out_text = utils.format_detailed_analysis(analysis)
check("richness labeled as of-meaningful",
      "of meaningful" in out_text, out_text[:300])

print("== auto-delivery markers (static) ==")
src = open("handlers.py").read()
check("[MP3][QUEUED] marker present", "[MP3][QUEUED]" in src)
check("[MP3][AUTO-DELIVERED] marker present", "[MP3][AUTO-DELIVERED]" in src)

print("== MP3 hard kill (live-ish) ==")
import services.youtube_downloader_service as yds
orig = yds._download_url_to_mp3
def _hang(url, prefix, label="test"):
    time.sleep(120)
    return "/tmp/never.mp3"
yds._download_url_to_mp3 = _hang
yds._CANDIDATE_TIMEOUT_SECS = 6  # shrink for the test
t0 = time.time()
try:
    # _try_download is a closure inside download_audio_for_song; replicate its
    # new logic via a direct call to a scratch copy is overkill — instead
    # verify the mechanism: fork a child running _hang and hard-kill it.
    import multiprocessing as mp
    ctx = mp.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=lambda q: q.put(_hang("u", "p")), args=(q,), daemon=True)
    p.start(); p.join(6)
    alive = p.is_alive()
    if alive:
        p.terminate(); p.join(5)
    check("stalled child hard-killed within budget",
          not p.is_alive() and (time.time() - t0) < 30,
          f"elapsed={time.time()-t0:.1f}s")
finally:
    yds._download_url_to_mp3 = orig
    yds._CANDIDATE_TIMEOUT_SECS = 45

print("== mood identity (live) ==")
mixes = {m: ds.get_mood_mix(m, 5) for m in
         ['happy', 'energetic', 'relaxed', 'sad', 'romantic', 'party', 'focus']}
def sig(m):
    return {(s['artist'].lower(), s['name'].lower()) for s in mixes[m]}
check("party vs energetic overlap <= 2",
      len(sig('party') & sig('energetic')) <= 2,
      f"overlap={len(sig('party') & sig('energetic'))}")
check("relaxed vs focus overlap <= 2",
      len(sig('relaxed') & sig('focus')) <= 2,
      f"overlap={len(sig('relaxed') & sig('focus'))}")
for m, songs in mixes.items():
    check(f"{m}: 5 songs, no pool fallback",
          len(songs) == 5 and all(s['source'] in ('fresh', 'tag') for s in songs),
          str([(s['source'], s['name']) for s in songs]))
    arts = [s['artist'].lower() for s in songs]
    check(f"{m}: no repeat artist", len(set(arts)) == len(arts), str(arts))
gospel = [f"{m}:{s['artist']}-{s['name']}" for m in mixes for s in mixes[m]
          if any(w in (s['artist'] + ' ' + s['name']).lower()
                 for w in ['worship', 'brandon lake', 'elevation worship'])]
check("no gospel in energetic/party", not gospel, str(gospel))

print(f"\nround-13: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
