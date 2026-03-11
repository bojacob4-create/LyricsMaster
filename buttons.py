from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _cb(action, query):
    data = f"{action}:{query}"
    if len(data.encode('utf-8')) > 64:
        max_q = 64 - len(action) - 1
        query = query[:max_q]
        data = f"{action}:{query}"
    return data


def lyrics_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
            InlineKeyboardButton("🌍 Translate", callback_data=_cb("translate", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🎧 Similar", callback_data=_cb("recommend", query)),
        ],
    ])


def song_dashboard_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Full Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
        ],
        [
            InlineKeyboardButton("🌍 Translate", callback_data=_cb("translate", query)),
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
        ],
        [
            InlineKeyboardButton("🎧 Similar", callback_data=_cb("recommend", query)),
        ],
    ])


def artist_buttons(artist_name, top_songs=None):
    rows = []
    if top_songs:
        for s in top_songs[:5]:
            song_query = f"{artist_name} - {s}"
            rows.append([InlineKeyboardButton(f"🎵 {s}", callback_data=_cb("song", song_query))])
    rows.append([
        InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", artist_name)),
        InlineKeyboardButton("🎧 Similar", callback_data=_cb("recommend", artist_name)),
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
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", query)),
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
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", query)),
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
            InlineKeyboardButton("📺 YouTube", callback_data=_cb("youtube", query)),
        ],
        [
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", query)),
        ],
    ])


def recommend_pick_buttons(artist_name, top_songs):
    rows = []
    for s in top_songs[:5]:
        song_query = f"{artist_name} - {s}"
        rows.append([InlineKeyboardButton(f"🎵 {s}", callback_data=_cb("recommend", song_query))])
    return InlineKeyboardMarkup(rows)


def artist_analyze_buttons(artist_name):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎤 Artist Profile", callback_data=_cb("artist", artist_name)),
            InlineKeyboardButton("🎵 Song Dashboard", callback_data=_cb("artistsongs", artist_name)),
        ],
        [
            InlineKeyboardButton("📺 YouTube", callback_data=_cb("youtube", artist_name)),
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", artist_name)),
        ],
    ])
