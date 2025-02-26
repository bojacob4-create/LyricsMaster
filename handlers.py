import logging
from telegram import Update
from telegram.ext import CallbackContext
from services.lyrics_service import get_song_lyrics
from services.translator_service import translate_to_arabic
from services.recommendation_service import get_similar_songs, format_recommendations
from services.quiz_service import start_quiz, check_answer, get_quiz_stats, end_quiz, get_next_question
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
        logger.info(f"User {user_id} started a lyrics quiz")

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
        logger.info(f"Sent first quiz question to user {user_id}")

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
        if "No more questions available" in feedback:
            update.message.reply_text(f"{feedback}\n\n{end_quiz(user_id)}")
            return

        quiz_data = get_next_question(user_id)
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
        logger.info(f"Processed quiz answer from user {user_id}")

    except Exception as e:
        logger.error(f"Error processing quiz answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong processing your answer.\n"
            "Try /quiz to start a new game! 🔄"
        )