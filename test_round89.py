"""Round 89: QR tile corner radius aligned to the album art tile (40px).

User-approved (2026-09-27):
- The QR tile's container + shadow used radius=46 while the album art tile
  used radius=40. The QR tile is smaller (~252px vs 300px), so it also read
  proportionally rounder (~18% vs ~13%). Both now use radius=40, so the two
  bottom tiles share the exact same corner roundness. The QR *modules*
  layer keeps radius=28 (~14%), which already rhymes with the art.
- Deliberate non-change: the QR tile footprint stays ~252px outer (modules
  ~200px + 26px padding). Scaling to 300px would give the high-contrast
  black-and-white QR equal visual billing with the artwork and undo the
  round-59 hierarchy (art = hero, QR = secondary).
- TEMPLATE_VERSION 4 -> 5 retires the v4 cached renders.
Run: ../venv/bin/python test_round89.py
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


def check_true(name, cond):
    check(name, bool(cond), True)


# ── Template version bumped (version-agnostic: must be >= 5, the round-89
# value; later rounds bump it further without breaking this suite) ──
check_true("TEMPLATE_VERSION >= 5", sc.TEMPLATE_VERSION >= 5)
check("version in cache filename",
      os.path.basename(sc.card_cache_path("ab12cd34ef56")),
      f"ab12cd34ef56_v{sc.TEMPLATE_VERSION}.png")

# ── No stale 46px radius left anywhere in the renderer ──
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "services", "share_card.py")).read()
check_true("no radius=46 remains in share_card.py", "radius=46" not in src)

# ── Render a card and measure both tiles' top-left corner arcs ──
deep_link = "https://t.me/MGLyricsbot?start=share_46e54bb1d7"
art = Image.new("RGB", (1200, 1200), (255, 255, 255))  # white: razor edge
png = sc.render_share_card("Teddy Swims", "Lose Control",
                           ["line one", "line two"], art, deep_link)
img = Image.open(io.BytesIO(png)).convert("RGB")
check("render size", img.size, (1080, 1350))
# Guard: we must be measuring the real template, not the never-raise fallback.
check_true("art tile present in render",
           sum(img.getpixel((700, 1000))) > 700)

# Replicate the renderer's QR geometry exactly.
qr = qrcode.QRCode(box_size=10, border=2)
qr.add_data(deep_link)
qr.make(fit=True)
n = len(qr.get_matrix())
box = max(2, 200 // n)
size = box * n
pad = 26
zone_y = 955
art_cy = zone_y + 150
q_cx, q_cy = 270, art_cy
qx0, qy0 = q_cx - size // 2, q_cy - size // 2

# Deliberate non-change: QR tile footprint stays well under 300px.
check_true(f"qr tile outer {size + 2 * pad}px < 280px (not scaled to 300)",
           size + 2 * pad < 280)


def corner_arc_d(im, cx, cy):
    """Distance along the 45° diagonal from a tile's outer corner to where
    the tile fill begins. For a rounded rect of radius r the fill starts
    at d = r*(1 - 1/sqrt(2)): r=40 -> 11.72, r=46 -> 13.47 (non-overlapping
    on a 1px grid, since PIL draws hard edges)."""
    px = im.load()

    def lum(x, y):
        r, g, b = px[x, y]
        return 0.299 * r + 0.587 * g + 0.114 * b

    samples = [lum(cx + d, cy + d) for d in range(32)]
    outside = sum(samples[2:7]) / 5.0
    inside = sum(samples[18:24]) / 5.0
    mid = (outside + inside) / 2.0
    for d in range(8, 20):
        if samples[d] >= mid:
            return d
    return None


d_qr = corner_arc_d(img, qx0 - pad, qy0 - pad)   # QR container top-left
d_art = corner_arc_d(img, 810 - 150, zone_y)     # art tile top-left
check_true(f"qr container arc measured at d={d_qr} (r=40 -> ~11.7)",
           d_qr is not None and 11.0 <= d_qr < 13.4)
check_true(f"art tile arc measured at d={d_art} (r=40 -> ~11.7)",
           d_art is not None and 11.0 <= d_art < 13.4)
check_true(f"both tiles share the same roundness (|{d_qr}-{d_art}|<=1)",
           d_qr is not None and d_art is not None and abs(d_qr - d_art) <= 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
