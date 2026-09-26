"""Round 61: QR baseline tuck. Run: ../venv/bin/python test_round61.py

The QR assembly (tile + caption) rides slightly above center so the
caption tucks just inside the artwork's bottom edge instead of
dangling past it — near-alignment read as a droop. Container padding
also grew 20 -> 26px for more breathing room.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

import services.share_card as sc

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


png = sc.render_share_card("Adele", "Hello", ["line one"], None,
                           "https://t.me/MGLyricsbot?start=share_x")
im = Image.open(io.BytesIO(png)).convert("RGB")
px = im.load()

ART_BOTTOM = 955 + 300  # zone_y + art size: the layout contract


def _bright(x, y):
    return sum(px[x, y]) / 3


# Caption bottom: last row in the caption's x-range brighter than the
# background (caption text ~138, background < 90). Scan stops before
# the footer (top ~1294).
cap_bottom = 0
for y in range(1150, 1290):
    if max(_bright(x, y) for x in range(170, 361, 4)) > 105:
        cap_bottom = y

check(f"caption bottom ({cap_bottom}) tucks inside art bottom ({ART_BOTTOM})",
      cap_bottom < ART_BOTTOM - 5, True)
check("caption stays near the baseline (not floating)",
      cap_bottom > ART_BOTTOM - 20, True)
check("render size unchanged", im.size, (1080, 1350))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
