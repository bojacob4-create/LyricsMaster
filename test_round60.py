"""Round 60: Share Card newcomer onboarding. Run: ../venv/bin/python test_round60.py

1. QR caption: tiny muted "Scan for lyrics & more" beneath the QR —
   whispers the payoff to a stranger without cluttering the card.
2. Share-arrival welcome: /start share_<token> now sends a one-line
   intro BEFORE the song card, so a cold arrival learns what the bot
   is instead of getting a card out of nowhere.
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


# ── 1. QR caption ─────────────────────────────────────────────────────────
check("caption text", sc.QR_CAPTION, "Scan for lyrics & more")

png = sc.render_share_card("Adele", "Hello", ["line one"], None,
                           "https://t.me/MGLyricsbot?start=share_x")
im = Image.open(io.BytesIO(png)).convert("RGB")


def _band_mean(box):
    px = list(im.crop(box).getdata())
    return sum(sum(p) / 3 for p in px) / len(px)


# Caption band sits between the QR container (bottom ~1224) and the
# footer (top ~1294); compare its mean brightness against the blank
# strip directly below it (glow gradient is negligible across 1px).
def _band_mean(box):
    px = list(im.crop(box).getdata())
    return sum(sum(p) / 3 for p in px) / len(px)


band = _band_mean((170, 1228, 370, 1258))
blank = _band_mean((170, 1262, 370, 1288))
check(f"caption pixels present (band {band:.1f} vs bg {blank:.1f})",
      band > blank + 5, True)
check("render size unchanged", im.size, (1080, 1350))

# ── 2. share-arrival welcome ──────────────────────────────────────────────
w = h.SHARE_ARRIVAL_WELCOME
check("welcome mentions the share", "shared" in w.lower(), True)
check("welcome names the bot", "Lyrics Master" in w, True)
for kw in ("lyrics", "translation", "MP3", "recommendations"):
    check(f"welcome sells '{kw}'", kw in w, True)


class _Msg:
    def __init__(self):
        self.sent = []

    def reply_text(self, text, **kw):
        self.sent.append((text, kw))


class _User:
    id = 42
    first_name = "New"


class _Update:
    def __init__(self):
        self.message = _Msg()
        self.effective_user = _User()


class _Context:
    def __init__(self, args):
        self.args = args


upd, ctx = _Update(), _Context(["share_testtoken123"])
with patch("services.share_card.lookup_share_token",
           return_value="The Weeknd - Blinding Lights"), \
     patch.object(h, "song_command") as song_mock:
    h.start_command(upd, ctx)

check("welcome sent exactly once", len(upd.message.sent), 1)
sent_text, sent_kw = upd.message.sent[0]
check("welcome text used", sent_text, h.SHARE_ARRIVAL_WELCOME)
check("welcome uses Markdown", sent_kw.get("parse_mode"), "Markdown")
check("song card still follows", song_mock.call_count, 1)
check("token resolved into song args",
      ctx.args, ["The", "Weeknd", "-", "Blinding", "Lights"])

# Unknown token: falls through to the normal welcome (no share intro,
# no song card) — stranger with a stale link isn't stranded.
upd2, ctx2 = _Update(), _Context(["share_staletoken"])
with patch("services.share_card.lookup_share_token", return_value=None), \
     patch.object(h, "song_command") as song_mock2:
    h.start_command(upd2, ctx2)
check("stale token: no song card", song_mock2.call_count, 0)
check("stale token: normal welcome sent",
      any("Welcome" in t for t, _ in upd2.message.sent), True)
check("stale token: share intro NOT sent",
      all(t != h.SHARE_ARRIVAL_WELCOME for t, _ in upd2.message.sent), True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
