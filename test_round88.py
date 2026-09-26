"""Round 88: 1200px artwork + QR caption removal. Run: ../venv/bin/python test_round88.py

User-approved (2026-09-26):
1. Artwork fidelity — the 600px iTunes asset looks soft next to the
   2x-supersampled type/QR. Fetch 1200x1200, falling back to 600px when a
   catalog asset lacks the bigger file.
2. Caption Option A — remove the "Scan for lyrics & more" caption under
   the QR. The Telegram message caption already says "Scan the QR…", so
   the on-card caption was pure redundancy, and it made the left tile
   bottom-heavy. The QR tile now centers exactly on the artwork's
   vertical center for perfect bottom symmetry.
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


# ── Artwork URL upgrade ──
check("100px -> 1200px",
      sc.upgrade_artwork_url("https://x/100x100bb.jpg"),
      "https://x/1200x1200bb.jpg")
check("empty stays empty", sc.upgrade_artwork_url(""), "")
check("None stays empty", sc.upgrade_artwork_url(None), "")

# ── Artwork fallback URL ──
check("1200 -> 600 fallback",
      sc.artwork_fallback_url("https://x/1200x1200bb.jpg"),
      "https://x/600x600bb.jpg")
check("non-1200 URL has no fallback",
      sc.artwork_fallback_url("https://x/600x600bb.jpg"), None)
check("None has no fallback", sc.artwork_fallback_url(None), None)


def _fake_img():
    return Image.new("RGB", (1200, 1200), (90, 40, 20))


# ── resolve_share_artwork: 1200-first with 600 fallback ──
def _lookup_ok(artist, title, timeout=5):
    return {"artwork": "https://x/1200x1200bb.jpg"}


seen = []


def _dl_fallback(url, timeout=5, attempts=3):
    seen.append(url)
    return None if "1200x1200" in url else _fake_img()


img, transient = sc.resolve_share_artwork(
    "Teddy Swims", "Lose Control", _lookup_ok, _dl_fallback)
check("1200 miss falls back to 600", img is not None and not transient, True)
check("tried 1200 then 600", seen,
      ["https://x/1200x1200bb.jpg", "https://x/600x600bb.jpg"])


def _dl_ok(url, timeout=5, attempts=3):
    return _fake_img()


img, transient = sc.resolve_share_artwork(
    "Teddy Swims", "Lose Control", _lookup_ok, _dl_ok)
check("1200 hit needs no fallback", img is not None and not transient, True)


def _dl_dead(url, timeout=5, attempts=3):
    return None


img, transient = sc.resolve_share_artwork(
    "Teddy Swims", "Lose Control", _lookup_ok, _dl_dead)
check("both fail -> transient, no cache", (img, transient), (None, True))


def _lookup_plain(artist, title, timeout=5):
    return {"artwork": "https://x/600x600bb.jpg"}


seen2 = []


def _dl_plain(url, timeout=5, attempts=3):
    seen2.append(url)
    return None


img, transient = sc.resolve_share_artwork(
    "Teddy Swims", "Lose Control", _lookup_plain, _dl_plain)
check("non-1200 URL: single attempt, transient", (img, transient), (None, True))
check("no bogus fallback attempted", seen2, ["https://x/600x600bb.jpg"])

# ── Caption removed: old caption band is clean ──
png = sc.render_share_card(
    "Teddy Swims", "Lose Control", ["Line one here", "Line two here"],
    None, "https://t.me/MGLyricsbot?start=share_x")
img = Image.open(io.BytesIO(png)).convert("RGB")
check("output still 1080x1350", img.size, (1080, 1350))

# The old caption ("Scan for lyrics & more", light gray on dark) lived at
# x 150-390, y ~1235-1258. Bright-pixel count there is 0 now; simulating
# the old caption on the same render gives ~300 (metric validated).
bright = sum(1 for y in range(1235, 1259) for x in range(150, 391)
             if sum(img.getpixel((x, y))) > 330)
check("QR caption gone", bright, 0)

# ── Cache version bumped for the visual change ──
# (version-agnostic: later rounds bump TEMPLATE_VERSION further)
check("template version bumped",
      isinstance(sc.TEMPLATE_VERSION, int) and sc.TEMPLATE_VERSION >= 4, True)
check("version in cache filename",
      os.path.basename(sc.card_cache_path("ab12cd34ef56")),
      f"ab12cd34ef56_v{sc.TEMPLATE_VERSION}.png")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
