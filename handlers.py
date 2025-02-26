from telegram import Update
from telegram.ext import CallbackContext
from services.lyrics_service import get_song_lyrics
from services.spotify_service import get_top_tracks
from services.translator_service import translate_to_arabic
from utils import format_lyrics, format_top_tracks

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    welcome_message = (
        "👋 Welcome to MGLyricsBot!\n\n"
        "Available commands:\n"
        "/lyrics <artist> - <song> - Get song lyrics\n"
        "/toptracks - Get Spotify top 10 tracks\n"
        "/translate <artist> - <song> - Get Arabic translation of lyrics\n"
        "/help - Show this help message"
    )
    update.message.reply_text(welcome_message)

def help_command(update: Update, context: CallbackContext):
    """Send a message when the command /help is issued."""
    help_text = (
        "🎵 MGLyricsBot Help:\n\n"
        "Commands:\n"
        "1. Get lyrics: /lyrics artist - song\n"
        "   Example: /lyrics Ed Sheeran - Shape of You\n\n"
        "2. Top tracks: /toptracks\n"
        "   Shows current Spotify top 10 tracks\n\n"
        "3. Translate lyrics: /translate artist - song\n"
        "   Example: /translate Adele - Hello\n\n"
        "If you encounter any issues, make sure to use the correct format!"
    )
    update.message.reply_text(help_text)

def lyrics_command(update: Update, context: CallbackContext):
    """Handle the /lyrics command."""
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            update.message.reply_text(
                "⚠️ Please use the format: /lyrics artist - song"
            )
            return

        artist, song = query.split("-", 1)
        lyrics = get_song_lyrics(artist.strip(), song.strip())

        if not lyrics:
            update.message.reply_text("❌ Sorry, couldn't find lyrics for this song.")
            return

        formatted_lyrics = format_lyrics(lyrics)
        update.message.reply_text(formatted_lyrics)

    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def top_tracks_command(update: Update, context: CallbackContext):
    """Handle the /toptracks command."""
    try:
        tracks = get_top_tracks()
        if not tracks:
            update.message.reply_text("❌ Sorry, couldn't fetch top tracks.")
            return

        formatted_tracks = format_top_tracks(tracks)
        update.message.reply_text(formatted_tracks)

    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")

def translate_lyrics_command(update: Update, context: CallbackContext):
    """Handle the /translate command."""
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            update.message.reply_text(
                "⚠️ Please use the format: /translate artist - song"
            )
            return

        artist, song = query.split("-", 1)
        lyrics = get_song_lyrics(artist.strip(), song.strip())

        if not lyrics:
            update.message.reply_text("❌ Sorry, couldn't find lyrics for this song.")
            return

        translated_lyrics = translate_to_arabic(lyrics)
        if translated_lyrics:
            formatted_lyrics = format_lyrics(translated_lyrics)
            update.message.reply_text(formatted_lyrics)
        else:
            update.message.reply_text("❌ Sorry, couldn't translate the lyrics.")

    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")