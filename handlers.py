import logging
from telegram import Update
from telegram.ext import CallbackContext
from services.lyrics_service import get_song_lyrics
from services.translator_service import translate_to_arabic
from utils import format_lyrics, detect_song_mood # Added detect_song_mood

logger = logging.getLogger(__name__)

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")

    user_first_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hey {user_first_name}! Welcome to your Musical Companion! 🎵\n\n"
        "I'm here to help you discover and understand your favorite songs! 🎸\n\n"
        "Here's what I can do for you:\n"
        "🎤 /lyrics artist - song → Get song lyrics with mood analysis\n"
        "🌍 /translate artist - song → Get Arabic translation of lyrics\n"
        "💡 /help → Show more tips and examples\n\n"
        "Try me out! For example, type:\n"
        "/lyrics Ed Sheeran - Perfect"
    )
    update.message.reply_text(welcome_message)

def help_command(update: Update, context: CallbackContext):
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help")
    help_text = (
        "🎵 Let me show you how to use my features!\n\n"
        "1️⃣ To get song lyrics:\n"
        "   /lyrics artist - song\n"
        "   Example: /lyrics Ed Sheeran - Shape of You\n\n"
        "2️⃣ To get Arabic translation:\n"
        "   /translate artist - song\n"
        "   Example: /translate Adele - Hello\n\n"
        "🎯 Pro Tips:\n"
        "• Make sure to use the dash (-) between artist and song\n"
        "• Double-check the spelling of artist and song names\n"
        "• I'll also tell you the mood of the song! 🎭\n\n"
        "Ready to explore some music? Try one of the commands above! 🚀"
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
                "⚠️ Oops! I need both the artist and song name!\n\n"
                "Use this format: /lyrics artist - song\n"
                "For example: /lyrics Ed Sheeran - Perfect\n\n"
                "Give it another try! 🎵"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested lyrics for '{artist.strip()} - {song.strip()}'")

        # Send typing action
        update.message.chat.send_action(action="typing")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find those lyrics.\n\n"
                "Please check:\n"
                "• The spelling of the artist and song\n"
                "• If the song exists\n"
                "• Try another song from the same artist\n\n"
                "Need help? Use /help to see examples! 💡"
            )
            return

        # Detect song mood
        mood = detect_song_mood(lyrics)
        mood_emoji = {
            'happy': '😊',
            'sad': '😢',
            'romantic': '💖',
            'energetic': '⚡',
            'relaxed': '😌'
        }.get(mood, '🎵')

        # Format message with mood
        formatted_lyrics = format_lyrics(lyrics)
        response = (
            f"🎵 {artist.strip()} - {song.strip()}\n\n"
            f"Song mood: {mood_emoji} {mood.title()}\n\n"
            f"{formatted_lyrics}"
        )

        update.message.reply_text(response)
        logger.info(f"Successfully sent lyrics to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing lyrics command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while fetching the lyrics.\n"
            "Please try again in a moment! 🔄"
        )

def translate_lyrics_command(update: Update, context: CallbackContext):
    """Handle the /translate command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid translation query format")
            update.message.reply_text(
                "⚠️ Please use this format: /translate artist - song\n"
                "For example: /translate Adele - Hello\n\n"
                "Let's try again! 🎵"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested translation for '{artist.strip()} - {song.strip()}'")

        update.message.reply_text("🔄 Magic translation in progress... Please wait! ✨")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for translation: '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "😕 I couldn't find the lyrics for this song.\n"
                "Double-check the spelling and try again! 🔍"
            )
            return

        translated_lyrics = translate_to_arabic(lyrics)
        if translated_lyrics:
            formatted_lyrics = format_lyrics(translated_lyrics)
            response = (
                f"🎵 {artist.strip()} - {song.strip()}\n"
                f"🌍 Arabic Translation:\n\n"
                f"{formatted_lyrics}"
            )
            update.message.reply_text(response)
            logger.info(f"Successfully sent translated lyrics to user {user_id}")
        else:
            logger.warning(f"Translation failed for user {user_id}")
            update.message.reply_text(
                "😓 The translation genie is taking a break.\n"
                "Please try again in a few moments! 🧞‍♂️"
            )

    except Exception as e:
        logger.error(f"Error processing translate command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "🤖 Oops! My translation circuits got a bit tangled.\n"
            "Let's try that again in a moment! 🔄"
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