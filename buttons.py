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
        [
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
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
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
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
        InlineKeyboardButton("🎧 Similar", callback_data=_cb("recommend", f"artist:{artist_name}")),
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
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", query)),
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
            InlineKeyboardButton("📺 YouTube", callback_data=_cb("youtube", artist_name)),
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", f"artist:{artist_name}")),
        ],
    ])


def daily_song_buttons(query):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Full Lyrics", callback_data=_cb("lyrics", query)),
            InlineKeyboardButton("📊 Analyze", callback_data=_cb("analyze", query)),
        ],
        [
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", query)),
            InlineKeyboardButton("🎧 MP3", callback_data=_cb("mp3", query)),
        ],
        [
            InlineKeyboardButton("🎧 Similar Songs", callback_data=_cb("recommend", query)),
        ],
    ])


def subscribe_count_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 song per day", callback_data="subcount:1")],
        [InlineKeyboardButton("2 songs per day", callback_data="subcount:2")],
        [InlineKeyboardButton("3 songs per day", callback_data="subcount:3")],
    ])
