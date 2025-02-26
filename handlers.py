import logging
from telegram import Update
from telegram.ext import CallbackContext
from services.lyrics_service import get_song_lyrics
from services.translator_service import translate_to_arabic
from services.recommendation_service import get_similar_songs, format_recommendations
from services.quiz_service import start_quiz, check_answer, get_quiz_stats, end_quiz
from services.daily_song_service import (
    subscribe_user,
    unsubscribe_user,
    get_daily_song,
    format_daily_song,
    get_subscribed_users
)
from utils import (
    format_lyrics,
    detect_song_mood,
    get_song_statistics,
    format_statistics
)
from services.youtube_service import get_youtube_link, format_youtube_response

logger = logging.getLogger(__name__)

# Store active quiz sessions globally
active_quizzes = {}

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")

    user_first_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hey {user_first_name}! Welcome to your Musical Companion! 🎵\n\n"
        "I'm here to help you discover and understand your favorite songs! 🎸\n\n"
        "Here's what I can do for you:\n"
        "🎤 /lyrics artist - song → Get song lyrics with mood analysis\n"
        "📊 /stats artist - song → Get detailed song statistics\n"
        "🎵 /recommend artist - song → Get song recommendations\n"
        "🎮 /quiz → Play a fun lyrics guessing game!\n"
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
        "2️⃣ To get song statistics:\n"
        "   /stats artist - song\n"
        "   Example: /stats Adele - Hello\n\n"
        "3️⃣ To get song recommendations:\n"
        "   /recommend artist - song\n"
        "   Example: /recommend Taylor Swift - Love Story\n\n"
        "4️⃣ To play the lyrics quiz:\n"
        "   /quiz - Start a new quiz game\n"
        "   /endquiz - End the current game\n\n"
        "5️⃣ To get Arabic translation:\n"
        "   /translate artist - song\n"
        "   Example: /translate Adele - Hello\n\n"
        "🎯 Pro Tips:\n"
        "• Make sure to use the dash (-) between artist and song\n"
        "• Double-check the spelling of artist and song names\n"
        "• I'll analyze the mood and suggest similar songs! 🎭\n\n"
        "Ready to explore some music? Try one of the commands above! 🚀"
    )
    update.message.reply_text(help_text)

def quiz_command(update: Update, context: CallbackContext):
    """Handle the /quiz command to start a lyrics quiz."""
    user_id = update.effective_user.id
    try:
        quiz_data = start_quiz(user_id)
        if not quiz_data:
            update.message.reply_text(
                "😓 Oops! I couldn't start the quiz right now.\n"
                "Please try again in a moment! 🔄"
            )
            return

        snippet = quiz_data["current_question"]["snippet"]
        response = (
            "🎵 Welcome to the Lyrics Quiz! 🎮\n\n"
            "I'll show you some lyrics, and you guess the song!\n"
            "Format your answer as: artist - song\n\n"
            "Here's your first lyrics snippet:\n\n"
            f"{snippet}\n\n"
            "What song is this? Reply with your guess! 🤔\n"
            "Use /endquiz to finish the game early."
        )

        update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error in quiz command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong starting the quiz.\n"
            "Please try again in a moment! 🔄"
        )

def quiz_answer(update: Update, context: CallbackContext):
    """Handle quiz answers in regular messages."""
    user_id = update.effective_user.id
    try:
        answer = update.message.text
        if not answer or "-" not in answer:
            return  # Not a quiz answer

        is_correct, feedback = check_answer(user_id, answer)

        # Handle quiz completion
        if "Quiz completed!" in feedback:
            update.message.reply_text(f"{feedback}\n\n{end_quiz(user_id)}")
            return

        # Get current quiz data after answer check
        quiz_data = start_quiz(user_id)  # This will return the current quiz since it exists
        if not quiz_data or quiz_data["state"] != "active":
            update.message.reply_text("Quiz session ended. Start a new quiz with /quiz!")
            return

        stats = get_quiz_stats(user_id)
        snippet = quiz_data["current_question"]["snippet"]
        response = (
            f"{feedback}\n\n"
            f"{stats}\n\n"
            "Here's your next lyrics snippet:\n\n"
            f"{snippet}\n\n"
            "What song is this? Reply with your guess! 🤔"
        )

        update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error processing quiz answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong processing your answer.\n"
            "Try /quiz to start a new game! 🔄"
        )

def end_quiz_command(update: Update, context: CallbackContext):
    """Handle the /endquiz command."""
    user_id = update.effective_user.id
    try:
        logger.info(f"User {user_id} ended their quiz")
        result = end_quiz(user_id)
        update.message.reply_text(result)

    except Exception as e:
        logger.error(f"Error ending quiz for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong ending the quiz.\n"
            "Try /quiz to start a new game! 🔄"
        )

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

        # Get mood and statistics
        mood = detect_song_mood(lyrics)
        stats = get_song_statistics(lyrics)

        mood_emoji = {
            'happy': '😊',
            'sad': '😢',
            'romantic': '💖',
            'energetic': '⚡',
            'relaxed': '😌'
        }.get(mood, '🎵')

        # Format message with mood and brief stats
        formatted_lyrics = format_lyrics(lyrics)
        response = (
            f"🎵 {artist.strip()} - {song.strip()}\n\n"
            f"Song mood: {mood_emoji} {mood.title()}\n"
            f"Words: {stats['total_words']} | Lines: {stats['total_lines']} | "
            f"Vocabulary: {stats['vocabulary_richness']}%\n\n"
            f"{formatted_lyrics}\n\n"
            "Want more details? Try /stats with this song! 📊"
        )

        update.message.reply_text(response)
        logger.info(f"Successfully sent lyrics to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing lyrics command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while fetching the lyrics.\n"
            "Please try again in a moment! 🔄"
        )

def stats_command(update: Update, context: CallbackContext):
    """Handle the /stats command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid stats query format")
            update.message.reply_text(
                "⚠️ Oops! I need both the artist and song name!\n\n"
                "Use this format: /stats artist - song\n"
                "For example: /stats Ed Sheeran - Perfect\n\n"
                "Give it another try! 📊"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested stats for '{artist.strip()} - {song.strip()}'")

        # Send typing action
        update.message.chat.send_action(action="typing")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Please check the spelling and try again! 🔍"
            )
            return

        # Get statistics and format them
        stats = get_song_statistics(lyrics)
        formatted_stats = format_statistics(stats)

        response = (
            f"🎵 {artist.strip()} - {song.strip()}\n\n"
            f"{formatted_stats}\n\n"
            "Want to see the lyrics? Try /lyrics with this song! 🎤"
        )

        update.message.reply_text(response)
        logger.info(f"Successfully sent stats to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing stats command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while analyzing the song.\n"
            "Please try again in a moment! 🔄"
        )

def recommend_command(update: Update, context: CallbackContext):
    """Handle the /recommend command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid recommendation query format")
            update.message.reply_text(
                "⚠️ Oops! I need both the artist and song name!\n\n"
                "Use this format: /recommend artist - song\n"
                "For example: /recommend Taylor Swift - Love Story\n\n"
                "Give it another try! 🎵"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested recommendations for '{artist.strip()} - {song.strip()}'")

        # Send typing action
        update.message.chat.send_action(action="typing")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Please check the spelling and try again! 🔍"
            )
            return

        # Get song mood and recommendations
        mood = detect_song_mood(lyrics)
        recommendations = get_similar_songs(artist.strip(), song.strip(), mood)
        formatted_recommendations = format_recommendations(recommendations, f"{artist.strip()} - {song.strip()}")

        update.message.reply_text(formatted_recommendations)
        logger.info(f"Successfully sent recommendations to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing recommend command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while getting recommendations.\n"
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

def send_daily_song(context: CallbackContext):
    """Send daily song to all subscribed users."""
    try:
        logger.info("Starting daily song distribution")

        song, lyrics, analysis = get_daily_song()
        if not all([song, lyrics, analysis]):
            logger.error("Failed to get daily song")
            return

        message = format_daily_song(song, lyrics, analysis)

        # Send to all subscribed users
        subscribed_users = get_subscribed_users()

        for user_id, data in subscribed_users.items():
            try:
                context.bot.send_message(
                    chat_id=data["chat_id"],
                    text=message
                )
                logger.info(f"Sent daily song to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send daily song to user {user_id}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in daily song distribution: {str(e)}")

def subscribe_daily_command(update: Update, context: CallbackContext):
    """Handle the /subscribe command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        logger.info(f"User {user_id} requesting daily song subscription")

        if subscribe_user(user_id, chat_id):
            update.message.reply_text(
                "🎵 Awesome! You're now subscribed to Daily Song Discovery!\n\n"
                "I'll send you an interesting song every day with:\n"
                "• Lyrics analysis 📊\n"
                "• Mood detection 🎭\n"
                "• Fun facts about the song ✨\n\n"
                "Your first song will arrive tomorrow! 🎶\n"
                "Use /unsubscribe if you want to stop receiving daily songs."
            )
            logger.info(f"Successfully subscribed user {user_id}")
        else:
            update.message.reply_text(
                "😓 Oops! Something went wrong while subscribing.\n"
                "Please try again in a moment! 🔄"
            )
    except Exception as e:
        logger.error(f"Error in subscribe command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the subscription.\n"
            "Please try again later! 🔄"
        )

def unsubscribe_daily_command(update: Update, context: CallbackContext):
    """Handle the /unsubscribe command."""
    user_id = update.effective_user.id
    try:
        logger.info(f"User {user_id} requesting to unsubscribe from daily songs")

        if unsubscribe_user(user_id):
            update.message.reply_text(
                "👋 You've been unsubscribed from Daily Song Discovery.\n\n"
                "I'll stop sending daily songs. You can always\n"
                "subscribe again using /subscribe! 🎵"
            )
            logger.info(f"Successfully unsubscribed user {user_id}")
        else:
            update.message.reply_text(
                "😓 Oops! Something went wrong while unsubscribing.\n"
                "Please try again in a moment! 🔄"
            )
    except Exception as e:
        logger.error(f"Error in unsubscribe command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the unsubscription.\n"
            "Please try again later! 🔄"
        )

def youtube_command(update: Update, context: CallbackContext):
    """Handle the /youtube command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid youtube query format")
            update.message.reply_text(
                "⚠️ Please use this format: /youtube artist - song\n"
                "For example: /youtube Ed Sheeran - Perfect\n\n"
                "Let's try again! 🎵"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested YouTube link for '{artist.strip()} - {song.strip()}'")

        url = get_youtube_link(artist.strip(), song.strip())
        if not url:
            update.message.reply_text(
                "😕 Sorry, I couldn't get a YouTube link for this song.\n"
                "Please try again in a moment! 🔄"
            )
            return

        response = format_youtube_response(artist.strip(), song.strip(), url)
        update.message.reply_text(response)
        logger.info(f"Successfully sent YouTube link to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing youtube command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while getting the YouTube link.\n"
            "Please try again in a moment! 🔄"
        )