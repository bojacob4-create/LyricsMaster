"""Round 57: Share Card tests. Run: ../venv/bin/python test_round57.py"""
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


def check_true(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: condition false")


# ── Excerpt extraction ─────────────────────────────────────────────────────
LYR = (
    "[Verse 1]\n"
    "Hello from the other side\n"
    "I must have called a thousand times\n"
    "[Chorus]\n"
    "Hello from the other side\n"
    "I must have called a thousand times\n"
    "To tell you I am sorry\n"
    "But when I call you never seem to be home\n"
    "At all\n"
)
ex = sc.extract_excerpt(LYR)
check("chorus first line", ex[0], "Hello from the other side")
check("chorus max 5 lines", len(ex), 5)
check_true("no markers in excerpt",
           not any(l.startswith("[") for l in ex))

lyr2 = "[Verse 1]\nshort\n[Verse 2]\nline one\nline two\nline three\n"
check("no chorus -> longest section",
      sc.extract_excerpt(lyr2), ["line one", "line two", "line three"])

check("no markers -> first lines",
      sc.extract_excerpt("one\ntwo\nthree\nfour\nfive\nsix\n"),
      ["one", "two", "three", "four", "five"])
check("empty lyrics", sc.extract_excerpt(""), [])
check("none lyrics", sc.extract_excerpt(None), [])

# ── Color ──────────────────────────────────────────────────────────────────
r, g, b = sc.clamp_glow_color((255, 255, 0))
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
check_true("neon yellow tamed", lum <= 150)
check("white -> neutral gray", sc.clamp_glow_color((255, 255, 255)),
      (127, 127, 127))
check("black -> visible gray", sc.clamp_glow_color((10, 10, 10)),
      (76, 76, 76))
gr, gg, gb = sc.clamp_glow_color((128, 128, 128))
check_true("gray stays neutral", abs(gr - gg) <= 2 and abs(gg - gb) <= 2)
check("chromatic passthrough", sc.clamp_glow_color((200, 30, 30)),
      (200, 30, 30))

img = Image.new("RGB", (100, 100), (40, 80, 200))
check("dominant solid", sc.dominant_color(img), (40, 80, 200))

# ── v2: vibrant accent ─────────────────────────────────────────────────────
img_c = Image.new("RGB", (100, 100), (180, 100, 46))
check("vibrant picks saturated", sc.vibrant_color(img_c), (180, 100, 46))
img_g = Image.new("RGB", (100, 100), (128, 128, 128))
check("vibrant falls back on gray", sc.vibrant_color(img_g), (128, 128, 128))
ac = sc.accent_color((128, 128, 128))
mx, mn = max(ac), min(ac)
check_true("gray accent gains saturation", (mx - mn) > 40)
ac2 = sc.accent_color((200, 30, 30))
check_true("chromatic accent stays chromatic",
           ac2[0] > ac2[1] and ac2[0] > ac2[2])
check_true("accent is a 3-tuple",
           isinstance(ac, tuple) and len(ac) == 3)

# ── v3: QR blends into the card (no heavy white tile) ─────────────────────
png_qr = sc.render_share_card("Adele", "Hello", ["line one"], None,
                              "https://t.me/MGLyricsbot?start=share_x")
im_qr = Image.open(io.BytesIO(png_qr)).convert("RGB")
crop = im_qr.crop((100, 1330, 440, 1700))  # QR zone, left bottom
px = list(crop.getdata())
avg = sum(sum(p) // 3 for p in px) / len(px)
check_true("qr zone stays dark (no white block)", avg < 130)

# ── Render ─────────────────────────────────────────────────────────────────
art = Image.new("RGB", (600, 600), (40, 80, 200))
png = sc.render_share_card("Adele", "Hello", ["line one", "line two"], art,
                           "https://t.me/MGLyricsbot?start=share_x")
im = Image.open(io.BytesIO(png))
check("render size", im.size, (1080, 1920))
check_true("render is PNG", png[:8] == b"\x89PNG\r\n\x1a\n")

png2 = sc.render_share_card("Adele", "Hello", ["line one"], None,
                            "https://t.me/MGLyricsbot?start=share_x")
check("no-artwork render size",
      Image.open(io.BytesIO(png2)).size, (1080, 1920))

png3 = sc.render_share_card(
    "Red Hot Chili Peppers",
    "Californication (Remastered Deluxe Edition Bonus Track Version)",
    ["a", "b", "c", "d", "e"], art, "https://t.me/x")
check("long title no crash",
      Image.open(io.BytesIO(png3)).size, (1080, 1920))

# ── Tokens ─────────────────────────────────────────────────────────────────
_orig_token_file = sc._TOKEN_FILE
_orig_card_dir = sc._CARD_DIR
sc._TOKEN_FILE = "/tmp/test57_tokens.json"
sc._CARD_DIR = "/tmp/test57_cards"
try:
    if os.path.exists(sc._TOKEN_FILE):
        os.remove(sc._TOKEN_FILE)
    t1 = sc.get_share_token("Adele", "Hello")
    t2 = sc.get_share_token("adele", "hello")
    check("token deterministic", t1, t2)
    check_true("token length 10", len(t1) == 10)
    check("lookup round trip", sc.lookup_share_token(t1), "Adele - Hello")
    check("lookup unknown", sc.lookup_share_token("nope"), None)
    check("share link",
          sc.build_share_link("abc123"),
          "https://t.me/MGLyricsbot?start=share_abc123")
    p = sc.card_cache_path("abc123")
    check_true("cache dir created", os.path.isdir(sc._CARD_DIR))
    check_true("cache path", p.endswith("abc123.png"))
finally:
    sc._TOKEN_FILE = _orig_token_file
    sc._CARD_DIR = _orig_card_dir

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
