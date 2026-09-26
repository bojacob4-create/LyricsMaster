"""Round 59: Share Card bottom-zone balance. Run: ../venv/bin/python test_round59.py

- QR softened: rounded-corner mask rhyming with the album art, plus a faint
  rounded container behind it.
- QR sized down (~200px vs 300px art) so the artwork is the clear hero.
- Scan-safety invariant: corner rounding only clips the QR quiet zone.
"""
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode
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


def _matrix(url):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


URL = "https://t.me/MGLyricsbot?start=share_x"
m = _matrix(URL)
n = len(m)
box = max(2, 200 // n)

layer = sc._build_qr_layer(m, box)
check("qr layer size", layer.size, (box * n, box * n))
check("qr smaller than artwork (300px)", box * n < 300, True)
check("qr target ~200px", box * n <= 200, True)

check("corner pixel transparent (rounded)", layer.getpixel((0, 0))[3], 0)
check("module pixel inside mask opaque",
      layer.getpixel((15, 15))[3], 255)  # finder-pattern module
check("quiet-zone pixel transparent",
      layer.getpixel((6, 6))[3], 0)

# Scan-safety: corner cut depth must stay inside the quiet zone.
radius, border = 28, 2
cut_depth = radius - radius / math.sqrt(2)
quiet_zone = border * box
check(f"corner cut ({cut_depth:.1f}px) < quiet zone ({quiet_zone}px)",
      cut_depth < quiet_zone, True)

# Full render: geometry sane, and the QR never becomes a solid white
# block again (bright-pixel fraction stays well under a tile's ~67%).
png = sc.render_share_card("The Weeknd", "Blinding Lights",
                           ["I've been tryna call",
                            "I've been on my own for long enough"],
                           None, URL)
im = Image.open(io.BytesIO(png))
check("render size", im.size, (1080, 1350))
crop = im.crop((120, 960, 420, 1240))  # QR zone
px = list(crop.getdata())
bright_frac = sum(1 for p in px if sum(p) / 3 > 200) / len(px)
check(f"bright-pixel fraction {bright_frac:.2f} < 0.50", bright_frac < 0.50, True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
