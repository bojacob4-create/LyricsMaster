"""Round 58: Share Card correctness fixes. Run: ../venv/bin/python test_round58.py

1. Version-aware artwork: _itunes_track_lookup prefers the original track's
   artwork over a remix single ranking first on iTunes (the Blinding Lights /
   ROSALÍA remix case). Explicit version queries still get version art.
2. Excerpt de-noising: decorative ♪/symbol lines are dropped from excerpts.
3. Leading filler openers ("Yeah") are skipped so cards open on substance.
4. The no-artwork ♪ placeholder renders via a font that has the glyph.
"""
import io
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

import services.share_card as sc
import handlers as h

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


class _Resp:
    def __init__(self, results):
        self._results = results

    def json(self):
        return {"results": self._results}


def _itunes_hit(artist, track, album="Album"):
    return {
        "artistName": artist, "trackName": track,
        "artworkUrl100": "https://x/100x100bb.jpg",
        "primaryGenreName": "Pop", "collectionName": album,
    }


def _stub(results):
    def _get(*a, **k):
        return _Resp(results)
    return _get


REMIX_FIRST = [
    _itunes_hit("The Weeknd & ROSALÍA", "Blinding Lights (Remix)",
                "Blinding Lights (Remix) - Single"),
    _itunes_hit("The Weeknd", "Blinding Lights", "After Hours"),
    _itunes_hit("The Weeknd", "Blinding Lights (Live)", "Live At SoFi Stadium"),
]

# ── 1. version-aware artwork ──────────────────────────────────────────────
with patch.object(h.requests, "get", _stub(REMIX_FIRST)):
    m = h._itunes_track_lookup("The weeknd", "blinding lights")
check("remix-first: picks original artwork",
      (m["artist"], m["title"]), ("The Weeknd", "Blinding Lights"))
check("remix-first: artwork is original's",
      "After Hours" in m["album"], True)

with patch.object(h.requests, "get", _stub(REMIX_FIRST)):
    m = h._itunes_track_lookup("The weeknd", "blinding lights remix")
check("explicit remix query keeps remix art",
      m["title"], "Blinding Lights (Remix)")

with patch.object(h.requests, "get", _stub(REMIX_FIRST)):
    m = h._itunes_track_lookup("The weeknd", "blinding lights live")
check("explicit live query keeps live art",
      m["title"], "Blinding Lights (Live)")

only_qualified = [
    _itunes_hit("The Weeknd", "Blinding Lights (Remix)"),
    _itunes_hit("The Weeknd", "Blinding Lights (Live)"),
]
with patch.object(h.requests, "get", _stub(only_qualified)):
    m = h._itunes_track_lookup("The weeknd", "blinding lights")
check("no unqualified hit: falls back to first hit (old behavior)",
      m["title"], "Blinding Lights (Remix)")

with patch.object(h.requests, "get", _stub(
        [_itunes_hit("Rockabye Baby!", "Blinding Lights",
                      "Lullaby Renditions of the Weeknd")])):
    m = h._itunes_track_lookup("The weeknd", "blinding lights")
check("wrong artist still rejected", m, None)

with patch.object(h.requests, "get", _stub([])):
    m = h._itunes_track_lookup("The weeknd", "blinding lights")
check("empty iTunes results -> None", m, None)

check("empty term -> None", h._itunes_track_lookup("", ""), None)

check("qualifier detect: (Remix)",
      h._title_has_version_qualifier("Blinding Lights (Remix)"), True)
check("qualifier detect: bare remix",
      h._title_has_version_qualifier("blinding lights remix"), True)
check("qualifier detect: [Major Lazer Remix]",
      h._title_has_version_qualifier("Blinding Lights [Major Lazer Remix]"), True)
check("qualifier detect: plain title",
      h._title_has_version_qualifier("Blinding Lights"), False)
check("qualifier detect: feat",
      h._title_has_version_qualifier("Song (feat. Someone)"), True)

# ── 2. excerpt de-noising ─────────────────────────────────────────────────
noisy = ("Yeah\n♪\nI've been tryna call\nI've been on my own for long enough\n"
         "Maybe you can show me how to love, maybe\nI'm going through withdrawals\n"
         "And the city's cold and empty")
ex = sc.extract_excerpt(noisy)
check("noise ♪ line dropped", any("♪" in l for l in ex), False)
check("excerpt opens on substance", ex[0], "I've been tryna call")
check("excerpt still fills 5 lines", len(ex), 5)
check("filler skip pulls the next line in",
      ex[-1], "And the city's cold and empty")

check("ellipsis stub dropped",
      sc.extract_excerpt("...\nReal line one\nReal line two"), 
      ["Real line one", "Real line two"])

# ── 3. leading filler ─────────────────────────────────────────────────────
check("'Yeah,' with comma also skipped",
      sc.extract_excerpt("Yeah,\nLine one\nLine two")[0], "Line one")
check("multi-word opener kept",
      sc.extract_excerpt("Yeah I've been waiting\nLine two")[0],
      "Yeah I've been waiting")
chorus = "[Chorus]\nOh\nWe sing this part\nWe sing it loud"
check("chorus still preferred, filler skipped",
      sc.extract_excerpt(chorus), ["We sing this part", "We sing it loud"])
check("filler-only song keeps last line",
      sc.extract_excerpt("Yeah\nOh"), ["Oh"])
check("empty lyrics -> []", sc.extract_excerpt(""), [])
check("all noise -> []", sc.extract_excerpt("♪\n♫\n..."), [])

# ── 4. placeholder glyph path ─────────────────────────────────────────────
png = sc.render_share_card("A", "B", ["line one", "line two"], None,
                           "https://t.me/MGLyricsbot?start=share_x")
check("no-artwork render still 4:5",
      Image.open(io.BytesIO(png)).size, (1080, 1350))
f = sc._glyph_font(130)
check("glyph font loads a real TTF", f.path.endswith(".ttf"), True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
