import logging
from telegram import Update
from telegram.ext import CallbackContext
from services.lyrics_service import get_song_lyrics
from services.lastfm_service import get_top_tracks # Assumed this service now exists
from services.translator_service import translate_to_arabic
from utils import format_lyrics, format_top_tracks

logger = logging.getLogger(__name__)

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")
    welcome_message = (
        "👋 Welcome to MGLyricsBot!\n\n"
        "Available commands:\n"
        "/lyrics <artist> - <song> - Get song lyrics\n"
        "/toptracks - Get Last.fm top tracks\n" # Updated to reflect Last.fm
        "/translate <artist> - <song> - Get Arabic translation of lyrics\n"
        "/help - Show this help message"
    )
    update.message.reply_text(welcome_message)

def help_command(update: Update, context: CallbackContext):
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help")
    help_text = (
        "🎵 MGLyricsBot Help:\n\n"
        "Commands:\n"
        "1. Get lyrics: /lyrics artist - song\n"
        "   Example: /lyrics Ed Sheeran - Shape of You\n\n"
        "2. Top tracks: /toptracks\n"
        "   Shows current Last.fm top tracks\n\n" # Updated to reflect Last.fm
        "3. Translate lyrics: /translate artist - song\n"
        "   Example: /translate Adele - Hello\n\n"
        "If you encounter any issues, make sure to use the correct format!"
    )
    update.message.reply_text(help_text)

def lyrics_command(update: Update, context: CallbackContext):
    """Handle the /lyrics command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid lyrics query format")
            update.message.reply_text(
                "⚠️ Please use the format: /lyrics artist - song\n"
                "Example: /lyrics Ed Sheeran - Shape of You"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested lyrics for '{artist.strip()} - {song.strip()}'")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "❌ Sorry, couldn't find lyrics for this song.\n"
                "Please check the spelling and try again."
            )
            return

        formatted_lyrics = format_lyrics(lyrics)
        update.message.reply_text(formatted_lyrics)
        logger.info(f"Successfully sent lyrics to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing lyrics command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "❌ Sorry, something went wrong while fetching the lyrics.\n"
            "Please try again later."
        )

def top_tracks_command(update: Update, context: CallbackContext):
    """Handle the /toptracks command."""
    user_id = update.effective_user.id
    try:
        logger.info(f"User {user_id} requested top tracks")

        # Send initial message
        message = update.message.reply_text(
            "🎵 Fetching latest releases...\n"
            "This will just take a moment."
        )

        # Get tracks from Spotify
        tracks = get_top_tracks()

        if not tracks:
            logger.warning(f"No tracks returned for user {user_id}")
            message.edit_text(
                "❌ Sorry, we couldn't fetch the tracks right now.\n"
                "Please try again in a few minutes."
            )
            return

        # Format and send tracks
        formatted_tracks = format_top_tracks(tracks)
        message.edit_text(formatted_tracks)
        logger.info(f"Successfully sent {len(tracks)} tracks to user {user_id}")

    except Exception as e:
        logger.error(f"Error in top_tracks_command for user {user_id}: {str(e)}")
        error_message = (
            "❌ Sorry, there was a problem fetching the tracks.\n"
            "Please try again in a few minutes."
        )
        try:
            if 'message' in locals():
                message.edit_text(error_message)
            else:
                update.message.reply_text(error_message)
        except Exception as msg_error:
            logger.error(f"Error sending error message: {str(msg_error)}")
            update.message.reply_text("❌ An error occurred. Please try again later.")

def translate_lyrics_command(update: Update, context: CallbackContext):
    """Handle the /translate command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid translation query format")
            update.message.reply_text(
                "⚠️ Please use the format: /translate artist - song\n"
                "Example: /translate Adele - Hello"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested translation for '{artist.strip()} - {song.strip()}'")

        update.message.reply_text("🔄 Fetching and translating lyrics, please wait...")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for translation: '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "❌ Sorry, couldn't find lyrics for this song.\n"
                "Please check the spelling and try again."
            )
            return

        translated_lyrics = translate_to_arabic(lyrics)
        if translated_lyrics:
            formatted_lyrics = format_lyrics(translated_lyrics)
            update.message.reply_text(formatted_lyrics)
            logger.info(f"Successfully sent translated lyrics to user {user_id}")
        else:
            logger.warning(f"Translation failed for user {user_id}")
            update.message.reply_text(
                "❌ Sorry, couldn't translate the lyrics.\n"
                "Please try again later."
            )

    except Exception as e:
        logger.error(f"Error processing translate command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "❌ Sorry, something went wrong while translating the lyrics.\n"
            "Please try again later."
        )