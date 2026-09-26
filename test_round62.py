"""Round 62: song-dashboard button reorganization. Run: ../venv/bin/python test_round62.py

New intent-paired layout (was Lyrics/Analyze, Arabic/Translate,
Video/Similar, MP3, Share Card):
  [Lyrics] [MP3]  — read it, hear it
  [Analyze] [Similar Songs] — go deeper / find more
  [Video] [Translate to...] — watch / other languages
  [Arabic] [Share Card] — personal shortcut + social

Also: 'Similar Songs' moved off the 🎧 emoji (now 🔀) everywhere, since
🎧 already means MP3 — the duplication made the two blend together.
Callback actions are unchanged; this is labels + order only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import buttons as b

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def _rows(mk):
    return [[btn.text for btn in row] for row in mk.inline_keyboard]


def _actions(mk):
    return [[btn.callback_data.split(":")[0] for btn in row]
            for row in mk.inline_keyboard]


Q = "adele - hello"

# ── Dashboard layout ──────────────────────────────────────────────
rows = _rows(b.song_dashboard_buttons(Q))
check("dashboard has 4 rows", len(rows), 4)
check("row 1: read / hear", rows[0], ["🎵 Lyrics", "🎧 MP3"])
check("row 2: deeper / more", rows[1], ["📊 Analyze", "🔀 Similar Songs"])
check("row 3: watch / language", rows[2], ["📺 Video", "🌐 Translate to…"])
check("row 4: shortcut / social", rows[3], ["🌍 Arabic", "🖼️ Share Card"])

acts = sorted(a for r in _actions(b.song_dashboard_buttons(Q)) for a in r)
check("dashboard callback actions unchanged", acts,
      sorted(["lyrics", "mp3", "analyze", "recommend",
              "youtube", "translate_to", "translate", "sharecard"]))

# ── 🎧 means MP3 everywhere now ───────────────────────────────────
builders = [
    (b.song_dashboard_buttons, (Q,)),
    (b.lyrics_buttons, (Q,)),
    (b.no_lyrics_card_buttons, ("adele", "hello")),
    (b.artist_buttons, ("adele", ["hello"])),
    (b.recommend_buttons, (Q,)),
    (b.recommend_results_buttons, (Q, [])),
    (b.analyze_buttons, (Q,)),
    (b.stats_buttons, (Q,)),
    (b.ambiguous_buttons, (Q,)),
    (b.daily_song_buttons, (Q,)),
    (b.artist_analyze_buttons, ("adele",)),
]
bad_emoji, bad_similar = [], []
for builder, args in builders:
    for row in builder(*args).inline_keyboard:
        for btn in row:
            if btn.text.startswith("🎧") and "MP3" not in btn.text:
                bad_emoji.append(btn.text)
            if "Similar Songs" in btn.text and not btn.text.startswith("🔀"):
                bad_similar.append(btn.text)
check("no non-MP3 button uses 🎧", bad_emoji, [])
check("every Similar Songs uses 🔀", bad_similar, [])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
