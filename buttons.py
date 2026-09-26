from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from collections import OrderedDict
import hashlib


# ── Callback payload registry (round 6 QA) ─────────────────────────────────
# Telegram caps callback_data at 64 BYTES. The old code truncated by
# *characters*, so Arabic/CJK/emoji queries could still exceed the limit and
# Telegram rejected the whole message (BUTTON_DATA_INVALID). Worse, plain
# truncation silently corrupted long titles into different songs.
#
# Strategy: inline the query when it fits (the common case); otherwise store
# the full query server-side under a short token. Buttons stay valid and
# lossless. The registry is a bounded LRU — buttons are short-lived UI.
_CB_REGISTRY = OrderedDict()
_CB_REGISTRY_MAX = 1000
_CB_TOKEN_PREFIX = '~'


def _cb_token(query: str) -> str:
    digest = hashlib.sha1(query.encode('utf-8')).hexdigest()[:12]
    _CB_REGISTRY[digest] = query
    _CB_REGISTRY.move_to_end(digest)
    while len(_CB_REGISTRY) > _CB_REGISTRY_MAX:
        _CB_REGISTRY.popitem(last=False)
    return digest


def cb_resolve(param: str) -> str:
    """Resolve a callback param back to the full query (token or inline)."""
    if param.startswith(_CB_TOKEN_PREFIX):
        return _CB_REGISTRY.get(param[1:], param)
    return param


def _cb(action, query):
    data = f"{action}:{query}"
    if len(data.encode('utf-8')) <= 64:
        return data
    return f"{action}:{_CB_TOKEN_PREFIX}{_cb_token(query)}"


def lyrics_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
            InlineKeyboardButton("🌍 Arabic", callback_data=_cb("translate", query)),
        ],
        [
            InlineKeyboardButton("🌐 Translate to…", callback_data=_cb("translate_to", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
        [
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
    ])


def no_lyrics_card_buttons(artist, title):
    """Buttons for the no-lyrics fallback card (round 21).

    Everything here works without lyrics: video, audio, artist profile,
    lyrics-free recommendations and wiki.  Lyrics/Analyze/Translate are
    deliberately absent — there are no lyrics to show.
    """
    query = f"{artist} - {title}" if artist and title else (title or artist or "")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Watch Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🎧 Get MP3", callback_data=_cb("mp3", query)),
        ],
        [
            InlineKeyboardButton("👤 Artist Profile", callback_data=_cb("artist", artist or query)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("similar_nl", query)),
        ],
        [
            InlineKeyboardButton("📚 Wiki", callback_data=_cb("wiki", artist or query)),
        ],
    ])


def song_dashboard_buttons(query):
    # Round 62: intent-paired layout — read/hear first, then go deeper,
    # then watch/translate, then the personal shortcut + share.
    # (Was: Lyrics/Analyze, Arabic/Translate, Video/Similar, MP3, Share.)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
        [
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🌐 Translate to…", callback_data=_cb("translate_to", query)),
        ],
        [
            InlineKeyboardButton("🌍 Arabic", callback_data=_cb("translate", query)),
            InlineKeyboardButton("🖼️ Share Card", callback_data=_cb("sharecard", query)),
        ],
    ])


def artist_buttons(artist_name, top_songs=None, lookup_name=None):
    # Round-83c: lookup_name is the music-service-safe name (Wikipedia
    # disambiguation like "(singer)" stripped). Song/Video/Similar buttons
    # query music services, so they use it; the Wiki button keeps the
    # display name because it IS the Wikipedia page title. Defaults to
    # artist_name, so curated cards (no parens) are byte-identical.
    lookup_name = lookup_name or artist_name
    rows = []
    if top_songs:
        for s in top_songs[:5]:
            song_query = f"{lookup_name} - {s}"
            rows.append([InlineKeyboardButton(f"🎵 {s}", callback_data=_cb("song", song_query))])
    rows.append([
        InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", lookup_name)),
        InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", f"artist:{lookup_name}")),
    ])
    rows.append([
        InlineKeyboardButton("📚 Wiki", callback_data=_cb("wiki", artist_name)),
    ])
    return InlineKeyboardMarkup(rows)


def artist_summary_buttons(artist_name, top_songs):
    rows = []
    for s in top_songs[:5]:
        song_query = f"{artist_name} - {s}"
        rows.append([InlineKeyboardButton(f"🎵 {s}", callback_data=_cb("song", song_query))])
    rows.append([
        InlineKeyboardButton("👤 Full Artist Profile", callback_data=_cb("artist", artist_name)),
    ])
    return InlineKeyboardMarkup(rows)


def song_list_buttons(songs):
    rows = []
    for s in songs:
        query = f"{s['artist']} - {s['song']}"
        rows.append([InlineKeyboardButton(f"🎵 {s['song']}", callback_data=_cb("song", query))])
    return InlineKeyboardMarkup(rows)


def recommend_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
    ])


def trending_buttons(first_song_query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", first_song_query)),
            InlineKeyboardButton("🎶 Song Dashboard", callback_data=_cb("song", first_song_query)),
        ],
    ])


def analyze_buttons(query, artist_name=None):
    artist_val = artist_name if artist_name else query
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
        ],
        [
            InlineKeyboardButton("👤 Artist", callback_data=_cb("artist", artist_val)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
        [
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
    ])


def stats_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
    ])


def ambiguous_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎤 Artist Profile", callback_data=_cb("artist", query)),
            InlineKeyboardButton("🎵 Song Dashboard", callback_data=_cb("song", query)),
        ],
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
        ],
        [
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
    ])


def recommend_pick_buttons(artist_name, top_songs):
    rows = []
    for s in top_songs[:5]:
        song_query = f"{artist_name} - {s}"
        rows.append([InlineKeyboardButton(f"🎵 {s}", callback_data=_cb("song", song_query))])
    return InlineKeyboardMarkup(rows)


def recommend_results_buttons(source_query, recommendations):
    """Buttons for recommend output: source-song actions + buttons for each recommended song."""
    rows = []
    rows.append([
        InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", source_query)),
        InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", source_query)),
    ])
    rows.append([
        InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", source_query)),
        InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", source_query)),
    ])
    if recommendations:
        rows.append([InlineKeyboardButton("── Recommended Songs ──", callback_data="noop:x")])
        for rec in recommendations[:5]:
            song_q = f"{rec['artist']} - {rec['name']}"
            rows.append([InlineKeyboardButton(f"🎵 {rec['name']} — {rec['artist']}", callback_data=_cb("song", song_q))])
    rows.append([InlineKeyboardButton("🔄 More like this", callback_data=_cb("more_recs", source_query))])
    return InlineKeyboardMarkup(rows)


def no_lyrics_similar_buttons(source_query, recommendations):
    """Buttons for the no-lyrics Similar Songs view (round 21).

    No Lyrics/Analyze buttons — the source track has no lyrics.  "More
    like this" re-runs the lyrics-free pipeline via the similar_more
    action instead of the lyrics-based more_recs.
    """
    rows = [
        [
            InlineKeyboardButton("▶️ Watch Video", callback_data=_cb("youtube", source_query)),
            InlineKeyboardButton("🎧 Get MP3", callback_data=_cb("mp3", source_query)),
        ],
    ]
    if recommendations:
        rows.append([InlineKeyboardButton("── Recommended Songs ──", callback_data="noop:x")])
        for rec in recommendations[:5]:
            song_q = f"{rec['artist']} - {rec['name']}"
            rows.append([InlineKeyboardButton(
                f"🎵 {rec['name']} — {rec['artist']}",
                callback_data=_cb("song", song_q))])
    rows.append([InlineKeyboardButton("🔄 More like this", callback_data=_cb("similar_more_nl", source_query))])
    return InlineKeyboardMarkup(rows)


def daily_picker_buttons(songs):
    """Compact picker buttons for multi-song daily delivery."""
    rows = []
    for s in songs:
        song_q = f"{s['artist']} - {s['song']}"
        rows.append([InlineKeyboardButton(f"🎵 {s['song']} — {s['artist']}", callback_data=_cb("song", song_q))])
    return InlineKeyboardMarkup(rows)


def artist_analyze_buttons(artist_name):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎤 Artist Profile", callback_data=_cb("artist", artist_name)),
            InlineKeyboardButton("🎵 Song Dashboard", callback_data=_cb("artistsongs", artist_name)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", artist_name)),
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", f"artist:{artist_name}")),
        ],
    ])


def daily_song_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
        [
            InlineKeyboardButton("🔀 Similar Songs", callback_data=_cb("recommend", query)),
        ],
    ])


def subscribe_count_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 song per day", callback_data="subcount:1")],
        [InlineKeyboardButton("2 songs per day", callback_data="subcount:2")],
        [InlineKeyboardButton("3 songs per day", callback_data="subcount:3")],
    ])


def mood_buttons():
    """Quick-reply mood picker for /mood (2 buttons per row)."""
    from services.discovery_service import MOOD_BUTTONS
    rows = []
    for i in range(0, len(MOOD_BUTTONS), 2):
        row = []
        for label, key in MOOD_BUTTONS[i:i + 2]:
            row.append(InlineKeyboardButton(label, callback_data=f"mood:{key}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def decade_buttons():
    """Decade picker for /throwback."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎸 80s", callback_data="decade:80s"),
            InlineKeyboardButton("📼 90s", callback_data="decade:90s"),
        ],
        [
            InlineKeyboardButton("💿 2000s", callback_data="decade:2000s"),
            InlineKeyboardButton("📱 2010s", callback_data="decade:2010s"),
        ],
    ])


def emoji_exit_buttons():
    """Exit-game button shown on every emoji-game message."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚪 Exit game", callback_data="emoji_exit:x")],
    ])
