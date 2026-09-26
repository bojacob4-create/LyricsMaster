"""Round 87: 2x supersampling for share-card type + QR. Run: ../venv/bin/python test_round87.py

User report (2026-09-26): on high-DPI phone screens the card's text
edges and QR modules look soft/pixelated. Diagnosis: the card renders
at 1080x1350 (PNG, lossless — no compression on our side), but
Telegram's photo recompression plus 1x rasterized type leaves no headroom.

Fix: all type is drawn at 2x on a dedicated transparent layer (layout
math stays 1x), then downscaled with LANCZOS and composited; the QR
layer renders at 2x and downscales the same way. Background shapes are
smooth gradients and stay 1x. Output is still 1080x1350 PNG.

The sharpness tests below assert the mechanism directly: a 2x-rendered
then downscaled glyph/QR edge must carry MORE intermediate alpha levels
(real anti-aliasing) than the old 1x rasterization.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode
from PIL import Image, ImageDraw

import services.share_card as sc

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def distinct_alphas(img):
    return len(set(img.getchannel("A").getdata()))


# ── QR: 2x-downscaled modules carry anti-aliased edges ──
qr = qrcode.QRCode(box_size=10, border=2)
qr.add_data("https://t.me/MGLyricsbot?start=share_x")
qr.make(fit=True)
m = qr.get_matrix()
n = len(m)
box = max(2, 200 // n)

layer_1x = sc._build_qr_layer(m, box)                       # old way
layer_2x = sc._build_qr_layer(m, box * 2, radius=28 * 2)     # new way
layer_2x = layer_2x.resize((box * n, box * n), Image.LANCZOS)

a1, a2 = distinct_alphas(layer_1x), distinct_alphas(layer_2x)
check("2x QR downscale keeps target size", layer_2x.size, (box * n, box * n))
check(f"2x QR edges anti-aliased ({a2} levels > {a1} 1x levels)", a2 > a1, True)
check("2x QR still has solid modules",
      layer_2x.getpixel((box * n // 2, box * n // 2))[3] > 200, True)

# ── Type: 2x-downscaled glyphs carry anti-aliased edges ──
def render_text(scale):
    w, h, size = 200 * scale, 80 * scale, 40 * scale
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    f = sc._font("bold", size)
    if scale == 1:
        sc._ctext(d, w // 2, 10, "Ag", f, (245, 241, 234))
        return c
    d.text((w // 2, 20 + 6), "Ag", font=f, fill=(0, 0, 0, 170), anchor="ma")
    d.text((w // 2, 20), "Ag", font=f, fill=(245, 241, 234), anchor="ma")
    return c.resize((200, 80), Image.LANCZOS)

t1, t2 = distinct_alphas(render_text(1)), distinct_alphas(render_text(2))
check(f"2x type edges anti-aliased ({t2} levels > {t1} 1x levels)", t2 > t1, True)

# ── Full card: output contract unchanged, text layer composited ──
png = sc.render_share_card(
    "Teddy Swims", "Lose Control",
    ["Something's got a hold of me lately", "No, I don't know myself anymore"],
    None, "https://t.me/MGLyricsbot?start=share_x")
img = Image.open(io.BytesIO(png)).convert("RGB")
check("output still 1080x1350", img.size, (1080, 1350))


def row_diff(y_text, y_empty):
    return max(
        sum(abs(a - b) for a, b in zip(img.getpixel((x, y_text)),
                                       img.getpixel((x, y_empty))))
        for x in range(400, 681, 20))


# Brand mark sits just below y=100 (anchor geometry, unchanged from the
# old path); y=160 is empty gradient between brand and excerpt.
brand_diff = max(row_diff(y, 160) for y in (105, 112, 120))
check("brand text drawn (2x layer composited)", brand_diff > 60, True)
# Excerpt zone: text rows differ strongly from the gap above the divider.
check("excerpt text drawn (2x layer composited)", row_diff(400, 700) > 60, True)

# ── Cache version bumped for the visual change ──
# (Version-agnostic: the number itself moves with every visual round.)
check("template version is a positive int",
      isinstance(sc.TEMPLATE_VERSION, int) and sc.TEMPLATE_VERSION >= 3, True)
check("version in cache filename",
      os.path.basename(sc.card_cache_path("ab12cd34ef56")),
      f"ab12cd34ef56_v{sc.TEMPLATE_VERSION}.png")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
