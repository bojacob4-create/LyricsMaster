"""Round-25 tests: the song card gets a photo header like the no-lyrics card.

Artwork comes from _itunes_track_lookup, which only returns a hit that
passes the round-20 relevance floor (no wrong-song artwork).  The photo is
used only when the card fits in a Telegram photo caption (<=1000 chars);
otherwise — or when artwork is missing/fails — the classic text card is
shown, silently.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


LYRICS = "Hello line one\nHello line two\nHello line three\nHello line four\nHello line five\n"


class FakeProcessing:
    def __init__(self):
        self.edited = None
        self.deleted = False

    def edit_text(self, t, **kw):
        self.edited = t
        self.edit_kwargs = kw

    def delete(self):
        self.deleted = True


class FakeMsg:
    def __init__(self):
        self.processing = FakeProcessing()
        self.photo_kwargs = None
        self.chat = MagicMock()

    def reply_text(self, t, **kw):
        return self.processing

    def reply_photo(self, *a, **kw):
        self.photo_kwargs = kw
        return MagicMock()


class FakeUpdate:
    def __init__(self):
        self.effective_user = MagicMock()
        self.effective_user.id = 4242
        self.message = FakeMsg()


class FakeContext:
    def __init__(self):
        self.args = ["Adele", "-", "Hello"]
        self.user_data = {}


def run_card(artwork_value, lyrics=LYRICS):
    """Run song_command with mocked services; return the FakeMsg."""
    upd = FakeUpdate()
    with patch.object(handlers, "search_lyrics_with_fallback",
                       return_value=("Adele", "Hello", lyrics, "ok")), \
         patch.object(handlers, "_is_artist_only_query", return_value=False), \
         patch.object(handlers, "detect_song_mood", return_value="sad"), \
         patch.object(handlers, "get_song_statistics",
                       return_value={"total_words": 100, "total_lines": 20,
                                     "vocabulary_richness": 60}), \
         patch.object(handlers, "get_youtube_link_info",
                       return_value={"url": "https://youtu.be/abc",
                                     "kind": "official", "is_live": False,
                                     "is_official": True,
                                     "title": "Adele - Hello (Official Music Video)",
                                     "alt": None}), \
         patch.object(handlers, "get_similar_songs",
                       return_value=[{"artist": "X", "name": "Y"}]), \
         patch.object(handlers, "detect_themes", return_value=["love"]), \
         patch.object(handlers, "_itunes_track_lookup",
                       return_value=artwork_value):
        handlers.song_command(upd, FakeContext())
    return upd.message


ART = {"artist": "Adele", "title": "Hello",
       "artwork": "https://is1-ssl.mzstatic.com/600x600.jpg",
       "genre": "Pop", "album": "25"}

# ── 1. Verified artwork -> photo card ──────────────────────────────────────
m = run_card(ART)
check("photo card: reply_photo called", m.photo_kwargs is not None)
check("photo card: uses the verified artwork URL",
      m.photo_kwargs and m.photo_kwargs.get("photo") == ART["artwork"])
check("photo card: caption is the full card text",
      m.photo_kwargs and m.photo_kwargs.get("caption", "").startswith("🎵 Adele - Hello"))
check("photo card: buttons attached",
      m.photo_kwargs and m.photo_kwargs.get("reply_markup") is not None)
check("photo card: processing message removed", m.processing.deleted is True)
check("photo card: no text edit", m.processing.edited is None)

# ── 2. No artwork -> classic text card ─────────────────────────────────────
m2 = run_card(None)
check("no artwork: no photo", m2.photo_kwargs is None)
check("no artwork: text card shown",
      m2.processing.edited is not None and "Adele - Hello" in m2.processing.edited)
check("no artwork: buttons attached",
      m2.processing.edit_kwargs.get("reply_markup") is not None)

# ── 3. Artwork present but empty string -> text card ────────────────────────
m3 = run_card({"artwork": ""})
check("empty artwork: text fallback", m3.photo_kwargs is None
      and m3.processing.edited is not None)

# ── 4. Card too long for a caption -> text card even with artwork ───────────
long_lyrics = "".join(f"{'w' * 300} line{i}\n" for i in range(6))
m4 = run_card(ART, lyrics=long_lyrics)
check("long card: no photo attempted", m4.photo_kwargs is None)
check("long card: full text card shown", m4.processing.edited is not None
      and len(m4.processing.edited) > 1000)

# ── 5. Artwork lookup exploding -> text card, no crash ──────────────────────
upd = FakeUpdate()
with patch.object(handlers, "search_lyrics_with_fallback",
                   return_value=("Adele", "Hello", LYRICS, "ok")), \
     patch.object(handlers, "_is_artist_only_query", return_value=False), \
     patch.object(handlers, "detect_song_mood", return_value="sad"), \
     patch.object(handlers, "get_song_statistics",
                   return_value={"total_words": 100, "total_lines": 20,
                                 "vocabulary_richness": 60}), \
     patch.object(handlers, "get_youtube_link", return_value="https://youtu.be/abc"), \
     patch.object(handlers, "get_similar_songs", return_value=[]), \
     patch.object(handlers, "detect_themes", return_value=[]), \
     patch.object(handlers, "_itunes_track_lookup", side_effect=RuntimeError("boom")):
    try:
        handlers.song_command(upd, FakeContext())
        crashed = False
    except Exception:
        crashed = True
check("lookup failure: no crash", not crashed)
check("lookup failure: text card shown",
      upd.message.processing.edited is not None)

print(f"\nround25: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
