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


def artist_buttons(artist_name):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Top Song", callback_data=_cb("song", artist_name)),
            InlineKeyboardButton("📺 Video", callback_data=_cb("youtube", artist_name)),
        ],
        [
            InlineKeyboardButton("📚 Wiki", callback_data=_cb("wiki", artist_name)),
            InlineKeyboardButton("🎧 Similar", callback_data=_cb("recommend", artist_name)),
        ],
    ])


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
