"""Behavior tests for round-2 fixes:
1. Unicode-aware word counting (accents no longer dropped).
2. Mood detection normalized by keyword-list size.
3. Themes shown in detailed analysis output.
4. recommend_command: artist-vs-song disambiguation + artist: prefix.
5. Pending-artist follow-up accepts artist corrections ("rush"->"Ayra Starr").
"""
import sys
sys.path.insert(0, '.')

passed, failed = [], []


def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" — {extra}" if extra and not cond else ""))


# ── 1. Word counting with accented words ─────────────────────────────────────
from utils import get_song_statistics

stats = get_song_statistics("Beyoncé na na na\ncafé au lait yeah\n")
# Words: beyoncé, na, na, na, café, au, lait, yeah = 8
check("accented words counted", stats['total_words'] == 8,
      f"got {stats['total_words']}")
check("lines counted", stats['total_lines'] == 2, f"got {stats['total_lines']}")

stats2 = get_song_statistics("hello world\nfoo bar baz\n")
check("plain english unchanged", stats2['total_words'] == 5,
      f"got {stats2['total_words']}")

# ── 2. Mood normalization ────────────────────────────────────────────────────
from utils import detect_song_mood

# 4 happy hits ("happy joy fun dance") vs 5 sad hits
# ("sad cry tears pain hurt"). Raw counts favor sad (5>4); normalized
# should favor happy (4/25 > 5/37).
lyrics = "happy joy fun dance\nsad cry tears pain hurt\n"
check("mood normalized (happy wins)", detect_song_mood(lyrics) == 'happy',
      f"got {detect_song_mood(lyrics)}")

# Clear sad song still sad
check("clear sad still sad",
      detect_song_mood("cry tears pain hurt broken alone\n") == 'sad')

# No keywords -> default
check("no keywords -> energetic", detect_song_mood("la la la\n") == 'energetic')

# ── 3. Themes appear in analysis output ──────────────────────────────────────
from utils import get_detailed_song_analysis, format_detailed_analysis

analysis = get_detailed_song_analysis(
    "love love kiss heart forever darling\nlove love kiss heart\n")
out = format_detailed_analysis(analysis)
check("themes shown in analysis", "🎨 Themes:" in out and "Romantic" in out,
      out[:200])
check("mood bars still present", "😊 Happy" in out or "💖 Romantic" in out)

# ── 4 & 5. Handler flows (mocked network) ────────────────────────────────────
import handlers
from handlers import (
    natural_language_handler, recommend_command,
    _pending_recommend_artist, _names_match, _query_matches_song,
)
import services.lyrics_service as lyrics_service
import services.nlp_router as nlp_router


class FakeChat:
    def send_action(self, action=None):
        pass


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat = FakeChat()
        self.sent = []

    def reply_text(self, text, **kw):
        self.sent.append((text, kw))
        return self


class FakeUpdate:
    def __init__(self, text=""):
        self.message = FakeMessage(text)
        self.effective_user = type('U', (), {'id': 4242})()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


check("names match (case-insensitive)", _names_match("Ayra Starr", "ayra starr"))
check("names match (containment)", _names_match("Rush", "Rush Band"))
check("names differ", not _names_match("Rush", "Ayra Starr"))
check("query matches song", _query_matches_song("rush", "Rush"))
check("query matches song (multiword)", _query_matches_song("blinding lights", "Blinding Lights"))
check("query mismatch", not _query_matches_song("rush", "Tom Sawyer"))

# --- 4a. /recommend rush -> artist-vs-song disambiguation ---
orig_search_cands = nlp_router.search_song_candidates
nlp_router.search_song_candidates = lambda q, **k: [
    {'artist': 'Troye Sivan', 'song': 'Rush', 'listeners': 1115760},
    {'artist': 'Rush', 'song': 'Tom Sawyer', 'listeners': 954490},
]
orig_is_artist = handlers._is_artist_only_query
handlers._is_artist_only_query = lambda q: True  # band Rush is a known artist
try:
    upd, ctx = FakeUpdate(), FakeContext(['rush'])
    recommend_command(upd, ctx)
    sent = upd.message.sent[-1] if upd.message.sent else ("", {})
    sent_text = sent[0]
    markup = sent[1].get('reply_markup')
    btn_texts = []
    if markup:
        for row in markup.inline_keyboard:
            for b in row:
                btn_texts.append(getattr(b, 'text', str(b)))
    check("recommend rush -> disambiguation asked",
          "could be an artist" in sent_text, sent_text[:80])
    check("disambiguation offers artist button",
          any('Artist: Rush' in t for t in btn_texts), str(btn_texts))
    check("disambiguation offers song buttons",
          any('Troye Sivan' in t for t in btn_texts), str(btn_texts))
    check("no pending artist set on disambiguation",
          4242 not in _pending_recommend_artist)
finally:
    nlp_router.search_song_candidates = orig_search_cands
    handlers._is_artist_only_query = orig_is_artist

# --- 4b. /recommend artist:Rush -> forced artist mode (no disambiguation) ---
orig_top = handlers._fetch_artist_top_songs
handlers._fetch_artist_top_songs = lambda a: ["Tom Sawyer", "Limelight"]
handlers._is_artist_only_query = lambda q: True
try:
    upd, ctx = FakeUpdate(), FakeContext(['artist:Rush'])
    recommend_command(upd, ctx)
    sent_text = upd.message.sent[-1][0] if upd.message.sent else ""
    check("artist: prefix -> song picker",
          "Which Rush song should I use" in sent_text, sent_text[:80])
    pend = _pending_recommend_artist.get(4242)
    check("pending stores artist+query dict",
          isinstance(pend, dict) and pend.get('artist') == 'Rush'
          and pend.get('query') == 'Rush',
          str(pend))
finally:
    handlers._fetch_artist_top_songs = orig_top
    handlers._is_artist_only_query = orig_is_artist

# --- 4c. /recommend adele (song candidates all by Adele) -> no disambiguation ---
nlp_router.search_song_candidates = lambda q, **k: [
    {'artist': 'Adele', 'song': 'Rolling in the Deep', 'listeners': 5},
]
handlers._is_artist_only_query = lambda q: True
orig_info = handlers.get_artist_info
handlers.get_artist_info = lambda q: {'name': 'Adele'}
handlers._fetch_artist_top_songs = lambda a: ["Hello", "Rolling in the Deep"]
try:
    upd, ctx = FakeUpdate(), FakeContext(['adele'])
    recommend_command(upd, ctx)
    sent_text = upd.message.sent[-1][0] if upd.message.sent else ""
    check("unambiguous artist -> straight to picker",
          "Which Adele song should I use" in sent_text, sent_text[:80])
finally:
    nlp_router.search_song_candidates = orig_search_cands
    handlers._is_artist_only_query = orig_is_artist
    handlers.get_artist_info = orig_info
    handlers._fetch_artist_top_songs = orig_top

# --- 5. Pending-artist correction: "rush" -> "Ayra Starr" ---
orig_search_info = lyrics_service.search_song_info


def fake_search_info(artist, song):
    # Mirror the real bidirectional service: finds Ayra Starr - Rush.
    if artist.lower() == 'rush' and song.lower() == 'ayra starr':
        return ('Ayra Starr', 'Rush', 'lyrics…')
    return None


lyrics_service.search_song_info = fake_search_info
captured = {}
orig_recommend = handlers.recommend_command


def fake_recommend(update, context):
    captured['args'] = list(context.args)


handlers.recommend_command = fake_recommend
try:
    _pending_recommend_artist[4242] = {'artist': 'Rush', 'query': 'rush'}
    upd, ctx = FakeUpdate("Ayra Starr"), FakeContext()
    natural_language_handler(upd, ctx)
    check("artist correction recovers song",
          captured.get('args') == ['Ayra', 'Starr', '-', 'Rush'],
          str(captured.get('args')))
    check("pending cleared after recovery", 4242 not in _pending_recommend_artist)
finally:
    lyrics_service.search_song_info = orig_search_info
    handlers.recommend_command = orig_recommend
    _pending_recommend_artist.pop(4242, None)

# --- 5b. Normal pending flow still works ("hello" for Adele) ---
lyrics_service.search_song_info = lambda a, s: ('Adele', 'Hello', 'lyrics…')
handlers.recommend_command = fake_recommend
try:
    captured.clear()
    _pending_recommend_artist[4242] = {'artist': 'Adele', 'query': 'adele'}
    upd, ctx = FakeUpdate("hello"), FakeContext()
    natural_language_handler(upd, ctx)
    check("normal pending song still works",
          captured.get('args') == ['Adele', '-', 'Hello'],
          str(captured.get('args')))
finally:
    lyrics_service.search_song_info = orig_search_info
    handlers.recommend_command = orig_recommend
    _pending_recommend_artist.pop(4242, None)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
