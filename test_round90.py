"""Round 90: artwork tile uses aspect-fill (object-fit cover), centered.

User-reported edge case (2026-09-27): for art with baked-in pillar-box
bars (e.g. Madison Beer "Make You Mine" -- the label ships a square file
with the vertical photo framed by dark side bars), the tile showed the
bars as empty gaps inside the 300px tile.

Diagnosis: the source file is already square (1200x1200), so a plain
cover-crop changes nothing -- the bars are image *content*. The fix is
two-stage: _strip_pillar_bars() detects full-height dark, near-uniform
columns and crops to the content box (no-op for clean art), then
ImageOps.fit(..., (300, 300), centering=(0.5, 0.5)) does a true
object-fit cover. Top/bottom strips are deliberately NOT touched: dark
bands there are often just dark parts of the photo itself.
- TEMPLATE_VERSION 5 -> 6 retires the v5 cached renders.
Run: ../venv/bin/python test_round90.py
"""
import io
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageChops

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


def make_letterboxed(size=400, bar=60):
    """Square art with dark pillar bars + noisy warm 'photo' center."""
    rng = random.Random(90)
    img = Image.new("RGB", (size, size), (16, 22, 28))
    px = img.load()
    for y in range(size):
        for x in range(bar, size - bar):
            px[x, y] = (200 + rng.randint(-20, 20),
                        120 + rng.randint(-15, 15),
                        80 + rng.randint(-15, 15))
    return img


def make_clean(size=400):
    """Square art with no bars: full-frame noisy warm photo."""
    rng = random.Random(91)
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (200 + rng.randint(-20, 20),
                        120 + rng.randint(-15, 15),
                        80 + rng.randint(-15, 15))
    return img


def lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


# ── Template version bumped ──
check("TEMPLATE_VERSION == 6", sc.TEMPLATE_VERSION, 6)
check("version in cache filename",
      os.path.basename(sc.card_cache_path("ab12cd34ef56")),
      "ab12cd34ef56_v6.png")

# ── _strip_pillar_bars unit behavior ──
lb = make_letterboxed()
stripped = sc._strip_pillar_bars(lb)
check("letterboxed art: bars stripped", stripped.size, (280, 400))

clean = make_clean()
same = sc._strip_pillar_bars(clean)
check("clean art: size unchanged", same.size, (400, 400))
check_true("clean art: pixel-identical",
           ImageChops.difference(clean, same).getbbox() is None)

narrow = make_letterboxed(bar=8)  # 16/400 = 4% < 5% threshold
check_true("narrow bars (<5%): left untouched",
           sc._strip_pillar_bars(narrow).size == (400, 400))

small = make_letterboxed(size=100, bar=15)
check_true("small image guard: left untouched",
           sc._strip_pillar_bars(small).size == (100, 100))

tall = Image.new("RGB", (300, 500), (200, 120, 80))  # truly vertical, no bars
check_true("vertical art without bars: strip is a no-op",
           sc._strip_pillar_bars(tall).size == (300, 500))

# ── Cover fill always yields exactly 300x300 ──
from PIL import ImageOps
for src_img in (stripped, clean, tall):
    out = ImageOps.fit(sc._strip_pillar_bars(src_img), (300, 300),
                       Image.LANCZOS, centering=(0.5, 0.5))
    check("cover output 300x300", out.size, (300, 300))

# ── Full render: tile is filled edge-to-edge, no bar gaps ──
deep_link = "https://t.me/MGLyricsbot?start=share_46e54bb1d7"
png = sc.render_share_card("Madison Beer", "Make You Mine",
                           ["I-I-I wanna feel, feel, feel"],
                           make_letterboxed(), deep_link)
img = Image.open(io.BytesIO(png)).convert("RGB")
check("render size", img.size, (1080, 1350))
# Art tile geometry from the renderer: ax=660, ay0=zone_y=955, 300x300.
# 10px inside the left edge, mid-height: with the old resize() this pixel
# sat inside the 45px-wide bar (dark); now it must be photo content.
check_true("tile left edge is photo content, not a bar",
           lum(img.getpixel((670, 1105))) > 80)
check_true("tile right edge is photo content, not a bar",
           lum(img.getpixel((950, 1105))) > 80)
check_true("tile center is photo content",
           lum(img.getpixel((810, 1105))) > 80)

# ── Full render with clean art still healthy ──
png2 = sc.render_share_card("Teddy Swims", "Lose Control",
                            ["line one", "line two"], make_clean(), deep_link)
img2 = Image.open(io.BytesIO(png2)).convert("RGB")
check("clean-art render size", img2.size, (1080, 1350))
check_true("art tile present in clean render",
           lum(img2.getpixel((700, 1000))) > 60)

# ── No stale plain-resize of the artwork left in the renderer ──
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "services", "share_card.py")).read()
check_true("artwork uses ImageOps.fit cover", "ImageOps.fit" in src)
check_true("no artwork_img.resize((300, 300)) remains",
           "artwork_img.resize" not in src)

print(f"round90: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
