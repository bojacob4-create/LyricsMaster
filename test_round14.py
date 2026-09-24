"""Round-14 tests: Quick Stats accuracy audit (user request 2026-09-24 —
"all data under Quick Stats, make sure it's accurate").

Fixes under test (all in utils.py unless noted):
1. Section markers ([Verse 1], [Chorus], …) are metadata, not lyric lines:
   get_song_statistics line count excludes them (word count already did),
   so Words and Lines can no longer disagree.
2. Word counting includes numeric tokens ("1999") — previously silently
   dropped, undercounting Words vs what a reader counts.
3. One shared vocabulary_label() scheme: the song card, /stats and /analyze
   used three different label/threshold sets for the same number.
4. Song-card lyrics previews (both dashboards in handlers.py) skip marker
   lines instead of showing "[Verse 1]" as a lyric.
5. analyze_rhyme_pattern ignores marker lines (two "[Chorus]" tags used to
   count as rhyming lines, inflating rhyme density).
6. detect_themes escapes keyword patterns (hardening, no behavior change).

Run from repo root: python3 test_round14.py
"""
import os, sys
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

from utils import (
    get_song_statistics, detect_themes, detect_song_mood,
    format_statistics, format_detailed_analysis, get_detailed_song_analysis,
    analyze_rhyme_pattern, vocabulary_label, is_section_marker_line,
)

LYRICS = (
    "[Verse 1]\n"
    "Party like it's 1999, yeah\n"
    "We gonna dance until the morning light\n"
    "[Chorus]\n"
    "Oh oh oh, celebrate tonight\n"
    "Dance dance dance till we feel alive\n"
    "[Verse 2]\n"
    "1999 was a really good year\n"
    "We had fun, no pain, no fear"
)

print("== 1. section markers are not lyric lines ==")
stats = get_song_statistics(LYRICS)
check("line count excludes 3 markers (6, not 9)", stats['total_lines'] == 6,
      f"got {stats['total_lines']}")
check("is_section_marker_line('[Verse 1]')", is_section_marker_line("[Verse 1]"))
check("is_section_marker_line('  [Pre-Chorus]  ')", is_section_marker_line("  [Pre-Chorus]  "))
check("inline tag is not a marker line", not is_section_marker_line("hello [Chorus]"))
check("plain lyric is not a marker line", not is_section_marker_line("we gonna dance"))

print("== 2. numbers count as words ==")
# …1999 appears twice; old code dropped both (35), fixed code counts them (37)
check("words includes both 1999s", stats['total_words'] == 37,
      f"got {stats['total_words']}")

print("== 3. one vocabulary label scheme everywhere ==")
check("label(85) == Rich", vocabulary_label(85) == "Rich")
check("label(70) == Rich (boundary)", vocabulary_label(70) == "Rich")
check("label(69.9) == Moderate", vocabulary_label(69.9) == "Moderate")
check("label(50) == Moderate (boundary)", vocabulary_label(50) == "Moderate")
check("label(49.9) == Repetitive", vocabulary_label(49.9) == "Repetitive")
check("label(0) == Repetitive", vocabulary_label(0) == "Repetitive")
fmt_stats = format_statistics(stats)
check("/stats uses shared label",
      f"— {vocabulary_label(stats['vocabulary_richness'])}" in fmt_stats, fmt_stats)
analysis = get_detailed_song_analysis(LYRICS)
fmt_analysis = format_detailed_analysis(analysis)
label = vocabulary_label(stats['vocabulary_richness'])
check("/analyze note matches card label band",
      ("Rich vocabulary" in fmt_analysis if label == "Rich"
       else "Moderate word variety" in fmt_analysis if label == "Moderate"
       else "Repetitive" in fmt_analysis), label)

print("== 4. previews skip marker lines ==")
preview_lines = [l.strip() for l in LYRICS.strip().split('\n')
                 if l.strip() and not is_section_marker_line(l)][:4]
check("no marker in first 4 preview lines",
      not any(is_section_marker_line(l) for l in preview_lines), str(preview_lines))
check("preview starts with a real lyric",
      preview_lines[0] == "Party like it's 1999, yeah", preview_lines[0])

print("== 5. rhyme analysis ignores markers ==")
r = analyze_rhyme_pattern("[Chorus]\nhello world\n[Chorus]\ngoodbye world")
check("marker lines not counted", r['total_lines'] == 2, f"got {r['total_lines']}")
check("only genuine rhymes counted", r['rhyme_density'] == 100.0,
      f"got {r['rhyme_density']}")  # world/world really do rhyme
r2 = analyze_rhyme_pattern("[Verse 1]\nhello sunshine\n[Chorus]\ngoodbye moonlight")
check("markers can't fake-rhyme", r2['rhyming_lines'] == 0,
      f"got {r2['rhyming_lines']}")

print("== 6. themes + mood still sane ==")
check("themes detects celebration", detect_themes(LYRICS) == ['celebration'],
      str(detect_themes(LYRICS)))
check("mood detects happy", detect_song_mood(LYRICS) == 'happy')
check("empty lyrics -> zero stats, no crash",
      get_song_statistics("")['total_words'] == 0
      and get_song_statistics(None)['total_lines'] == 0)
check("marker-only lyrics -> 0 lines", get_song_statistics("[Intro]\n[Chorus]")['total_lines'] == 0)

print("== 7. celebration keywords tuned (round-14b) ==")
# "Happy" never says party/dance/celebrate — 'clap'/'happiness'/'joy' catch it.
happy_lyrics = "Because I'm happy\nClap along if you feel like happiness is the truth\n" * 4
check("'Happy'-style anthem -> celebration first",
      detect_themes(happy_lyrics)[0] == 'celebration',
      str(detect_themes(happy_lyrics)))
# 'happy' itself stays OUT of the list: negation-blind matching would put
# 'celebration' on sad songs ("I'm not happy anymore").
sad_lyrics = "I'm not happy anymore\ntears fall down in the cold dark rain\n" * 3
check("sad song saying 'not happy' is not celebration",
      'celebration' not in detect_themes(sad_lyrics),
      str(detect_themes(sad_lyrics)))
check("clap is celebration", detect_themes("clap clap clap your hands\n" * 2)[0] == 'celebration')

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
