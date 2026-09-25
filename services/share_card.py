"""Round 57: Share Card — branded 1080x1920 story-format lyric cards.

A song-card button ("Share Card") renders a signature @MGLyricsbot image:
dark gradient template, lyric excerpt in bold centered type, an ambient glow
tinted with the album art's dominant color (clamped so contrast always holds),
the album artwork, and a QR code deep-linking to that exact song card in the
bot (t.me/MGLyricsbot?start=share_<token>).
"""
import colorsys
import hashlib
import io
import json
import logging
import os

import qrcode
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from utils import atomic_json_write, is_section_marker_line

logger = logging.getLogger(__name__)

W, H = 1080, 1920
BOT_USERNAME = "MGLyricsbot"

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKEN_FILE = os.path.join(_REPO_DIR, "share_tokens.json")
_CARD_DIR = os.path.join(_REPO_DIR, "share_cards")

_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


# ── Lyric excerpt ──────────────────────────────────────────────────────────

def extract_excerpt(lyrics, max_lines=5):
    """Return up to `max_lines` lyric lines for the card.

    Preference: the [Chorus] section (the singable hook) -> the longest
    section -> the first lines. Section markers are never included.
    """
    if not lyrics:
        return []
    # Split into (marker, lines) sections.
    sections = []
    cur_marker, cur_lines = None, []
    for raw in lyrics.splitlines():
        line = raw.strip()
        if is_section_marker_line(line):
            if cur_lines or cur_marker is not None:
                sections.append((cur_marker, cur_lines))
            cur_marker, cur_lines = line, []
        elif line:
            cur_lines.append(line)
    if cur_lines or cur_marker is not None:
        sections.append((cur_marker, cur_lines))

    def usable(lines):
        return [l for l in lines if l][:max_lines]

    # 1. Chorus first.
    for marker, lines in sections:
        if marker and "chorus" in marker.lower() and len(lines) >= 2:
            return usable(lines)
    # 2. Longest section.
    if sections:
        longest = max(sections, key=lambda s: len(s[1]))
        if len(longest[1]) >= 2:
            return usable(longest[1])
    # 3. First lines of the song.
    flat = [l for _, lines in sections for l in lines]
    return usable(flat)


# ── Share tokens (deep-link payloads) ──────────────────────────────────────

def get_share_token(artist, title):
    """Deterministic short token for an (artist, title) pair.

    Stored in share_tokens.json so /start share_<token> can reopen the exact
    song card. Deterministic => re-sharing the same song reuses the token and
    the cached card; the file only grows with newly shared songs.
    """
    artist = (artist or "").strip()
    title = (title or "").strip()
    key = f"{artist.lower()}|{title.lower()}"
    token = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    query = f"{artist} - {title}" if artist and title else (title or artist)
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if token not in data:
        data[token] = query
        try:
            atomic_json_write(_TOKEN_FILE, data)
        except Exception as e:
            logger.debug(f"[sharecard] token persist failed: {e}")
    return token


def lookup_share_token(token):
    """Return the stored 'Artist - Title' query for a token, else None."""
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(token)
    except Exception:
        return None


def build_share_link(token):
    return f"https://t.me/{BOT_USERNAME}?start=share_{token}"


def card_cache_path(token):
    os.makedirs(_CARD_DIR, exist_ok=True)
    return os.path.join(_CARD_DIR, f"{token}.png")


# ── Color ──────────────────────────────────────────────────────────────────

def dominant_color(img):
    """Most representative color of the artwork.

    Most-common color among mid-tone, reasonably saturated pixels; falls back
    to the average color. Never raises.
    """
    try:
        small = img.convert("RGB").resize((64, 64), Image.LANCZOS)
        colors = small.getcolors(64 * 64) or []
        colors.sort(key=lambda c: c[0], reverse=True)
        for _, (r, g, b) in colors:
            mx, mn = max(r, g, b), min(r, g, b)
            if 40 < (r + g + b) // 3 < 215 and (mx - mn) > 24:
                return (r, g, b)
        # Fallback: average.
        px = list(small.getdata())
        n = len(px)
        return tuple(sum(c[i] for c in px) // n for i in range(3))
    except Exception:
        return (90, 110, 200)


def clamp_glow_color(rgb):
    """Clamp a glow tint so text contrast always holds on the dark template.

    - Perceptual-luminance cap (WCAG weights): neon covers get tamed instead
      of nuking readability.
    - HLS lightness pinned to [0.30, 0.55]: black art still glows, white art
      can't haze out.
    - Saturation lifted to 0.45 for chromatic colors; achromatic (gray)
      colors stay neutral instead of inventing a hue.
    """
    try:
        r, g, b = (x / 255.0 for x in rgb)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if lum > 0.5:
            f = 0.5 / lum
            r, g, b = r * f, g * f, b * f
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l = max(0.30, min(0.55, l))
        if s >= 0.15:
            s = max(s, 0.45)
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return (int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return (90, 110, 200)


def fetch_artwork(url, timeout=10):
    """Download artwork -> PIL Image (RGB), or None. Never raises."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        logger.debug(f"[sharecard] artwork fetch failed: {e}")
        return None


# ── Rendering helpers ──────────────────────────────────────────────────────

def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _text_size(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return r - l, b - t


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _text_size(draw, t, font)[0] <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _vgrad(w, h, top, bottom):
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        base.putpixel((0, y), tuple(int(a + (b - a) * t)
                                   for a, b in zip(top, bottom)))
    return base.resize((w, h))


def _radial_glow(size, rgb, peak_alpha=64):
    """Small radial glow, meant to be scaled up + blurred by the caller."""
    s = 160
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    px = glow.load()
    c = (s - 1) / 2
    for y in range(s):
        for x in range(s):
            d = (((x - c) ** 2 + (y - c) ** 2) ** 0.5) / c
            if d <= 1:
                px[x, y] = rgb + (int(peak_alpha * (1 - d) ** 2),)
    return glow.resize((size, size), Image.LANCZOS)


def _rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _fit_excerpt(draw, lines, max_w, max_h):
    """Largest bold font (76 -> 36) such that wrapped lines fit max_w/max_h."""
    size = 76
    while size >= 36:
        font = _font(_FONT_BOLD, size)
        wrapped = []
        for ln in lines:
            wrapped.extend(_wrap(draw, ln, font, max_w))
        w = max((_text_size(draw, l, font)[0] for l in wrapped), default=0)
        h = len(wrapped) * int(size * 1.42)
        if w <= max_w and h <= max_h:
            return font, wrapped
        size -= 4
    font = _font(_FONT_BOLD, 36)
    wrapped = []
    for ln in lines:
        wrapped.extend(_wrap(draw, ln, font, max_w))
    return font, wrapped


# ── Card ───────────────────────────────────────────────────────────────────

def render_share_card(artist, title, excerpt_lines, artwork_img, deep_link):
    """Render the 1080x1920 share card. Returns PNG bytes. Never raises."""
    try:
        return _render(artist, title, excerpt_lines, artwork_img, deep_link)
    except Exception as e:
        logger.error(f"[sharecard] render failed: {e}", exc_info=True)
        # Last-resort: plain dark card with text, so the button never 500s.
        img = Image.new("RGB", (W, H), (10, 10, 14))
        d = ImageDraw.Draw(img)
        f = _font(_FONT_BOLD, 48)
        d.text((W // 2, H // 2), f"{artist} — {title}",
               font=f, fill=(240, 240, 245), anchor="mm")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def _render(artist, title, excerpt_lines, artwork_img, deep_link):
    glow_rgb = clamp_glow_color(dominant_color(artwork_img)
                               if artwork_img is not None else (90, 110, 200))

    # Base: dark vertical gradient.
    img = _vgrad(W, H, (18, 18, 30), (6, 6, 11)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Ambient glow behind the text zone.
    glow = _radial_glow(1150, glow_rgb, peak_alpha=88).filter(
        ImageFilter.GaussianBlur(60))
    img.alpha_composite(glow, (W // 2 - 575, 200))

    # Brand mark (no emoji — DejaVu has no color-emoji glyphs).
    brand = _font(_FONT_BOLD, 30)
    spaced = " ".join("LYRICS MASTER")
    bw, _ = _text_size(draw, spaced, brand)
    draw.text((W // 2 - bw // 2, 140), spaced, font=brand,
              fill=(150, 150, 165))

    # Excerpt, auto-fit into the central zone.
    font, wrapped = _fit_excerpt(draw, excerpt_lines, max_w=900, max_h=620)
    line_h = int(font.size * 1.42)
    total_h = len(wrapped) * line_h
    zone_top, zone_h = 470, 620
    y = zone_top + (zone_h - total_h) // 2
    for ln in wrapped:
        lw, _ = _text_size(draw, ln, font)
        draw.text((W // 2 - lw // 2, y), ln, font=font, fill=(246, 246, 250))
        y += line_h

    # Accent divider in the glow color (full-strength for the bar).
    bar_w, bar_h, bar_y = 130, 8, zone_top + zone_h + 28
    draw.rounded_rectangle([W // 2 - bar_w // 2, bar_y,
                            W // 2 + bar_w // 2, bar_y + bar_h],
                           radius=bar_h // 2, fill=glow_rgb)

    # Artist — Title (single line; wrapped only to avoid overflow, which is
    # clipped by design to protect the bottom zone).
    sub = _font(_FONT_BOLD, 44)
    headline = f"{artist} — {title}" if artist and title else (title or artist or "")
    head_lines = _wrap(draw, headline, sub, 900)
    if head_lines:
        lw, _ = _text_size(draw, head_lines[0], sub)
        draw.text((W // 2 - lw // 2, bar_y + 44), head_lines[0], font=sub,
                  fill=(232, 232, 238))

    # Bottom zone: album art (left) + QR (right). Kept above y~1760 so
    # story UIs (reply bars) don't cover it.
    zone_y = 1390
    art = artwork_img
    if art is not None:
        art_sq = art.resize((320, 320), Image.LANCZOS)
    else:
        art_sq = Image.new("RGB", (320, 320), (24, 24, 34))
        d2 = ImageDraw.Draw(art_sq)
        nf = _font(_FONT_REG, 150)
        nw, nh = _text_size(d2, "♪", nf)
        d2.text((160 - nw // 2, 160 - nh // 2 - 10), "♪", font=nf,
                fill=glow_rgb)
    img.alpha_composite(_rounded(art_sq, 40), (90, zone_y))

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(deep_link)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black",
                         back_color="white").convert("RGB")
    qimg = qimg.resize((300, 300), Image.NEAREST)
    tile = Image.new("RGB", (340, 340), (255, 255, 255))
    tile.paste(qimg, (20, 20))
    img.alpha_composite(_rounded(tile, 36), (650, zone_y - 10))

    cap = _font(_FONT_REG, 30)
    cap_text = "Scan to open this song"
    cw, _ = _text_size(draw, cap_text, cap)
    draw.text((650 + 170 - cw // 2, zone_y + 348), cap_text, font=cap,
              fill=(140, 140, 152))

    # Footer.
    foot = _font(_FONT_REG, 30)
    ft = f"@{BOT_USERNAME} · share the vibe"
    fw, _ = _text_size(draw, ft, foot)
    draw.text((W // 2 - fw // 2, H - 110), ft, font=foot, fill=(120, 120, 132))

    out = img.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
