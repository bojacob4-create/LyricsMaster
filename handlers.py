import logging
import os
from telegram import Update, BotCommand
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    MessageHandler,
    Filters,
    Updater
)
from telegram.error import TelegramError
from services.lyrics_service import get_song_lyrics
from services.translator_service import translate_to_arabic
from services.recommendation_service import get_similar_songs, format_recommendations
from services.quiz_service import (
    start_quiz, check_answer, get_quiz_stats, end_quiz,
    format_multiple_choice_options, active_quizzes
)
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
    format_statistics,
    get_detailed_song_analysis,
    format_detailed_analysis
)
from services.youtube_service import get_youtube_link, format_youtube_response
from app import app
from services.youtube_downloader_service import download_youtube_video, cleanup_video
from services.wikipedia_service import get_wikipedia_info

logger = logging.getLogger(__name__)


def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")

    user_first_name = update.effective_user.first_name
    welcome_message = (
        f"🎵 *Welcome to Your Musical Companion, {user_first_name}!* 🎸\n\n"
        "I'm your personal music assistant, ready to help you discover and enjoy music in new ways! ✨\n\n"
        "*Here's what I can do for you:*\n\n"
        "🎤 */lyrics* - Get song lyrics with mood analysis\n"
        "📊 */stats* - See detailed song statistics\n"
        "🎵 */recommend* - Discover similar songs\n"
        "🎮 */quiz* - Play a fun lyrics quiz\n"
        "🌍 */translate* - Get Arabic lyrics translation\n"
        "🎬 */youtube* - Find song on YouTube\n"
        "📥 */download* - Download YouTube videos\n"
        "📈 */analyze* - Get deep song analysis\n"
        "🔔 */subscribe* - Get daily song discoveries\n"
        "📚 */wiki* - Get Wikipedia info about artists\n\n"
        "*Quick Start:*\n"
        "Try */lyrics Ed Sheeran - Perfect* to see the magic! ✨\n\n"
        "Need help? Just type */help* for more details! 💫"
    )

    try:
        update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        # Fallback to plain text if markdown fails
        update.message.reply_text(
            welcome_message.replace('*', ''),
            disable_web_page_preview=True
        )


def help_command(update: Update, context: CallbackContext):
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help")
    help_text = (
        "🎵 *Musical Companion Guide* 🎸\n\n"
        "*Basic Commands:*\n"
        "▫️ */lyrics artist - song*\n"
        "   Get lyrics with mood analysis\n"
        "   Example: */lyrics Taylor Swift - Love Story*\n\n"
        "▫️ */stats artist - song*\n"
        "   View detailed song statistics\n"
        "   Example: */stats Adele - Hello*\n\n"
        "▫️ */recommend artist - song*\n"
        "   Find similar songs you might like\n"
        "   Example: */recommend Ed Sheeran - Shape of You*\n\n"
        "*Fun & Games:*\n"
        "▫️ */quiz* - Start a music quiz\n"
        "▫️ */endquiz* - End current quiz\n\n"
        "*Language & Analysis:*\n"
        "▫️ */translate artist - song*\n"
        "   Get Arabic translation\n"
        "▫️ */analyze artist - song*\n"
        "   Deep dive into song meaning\n\n"
        "*Media Features:*\n"
        "▫️ */youtube artist - song*\n"
        "   Find song on YouTube\n"
        "▫️ */download video_url*\n"
        "   Download YouTube videos\n\n"
        "*Information:*\n"
        "▫️ */wiki person_name*\n"
        "   Get Wikipedia information\n"
        "   Example: */wiki Taylor Swift*\n\n"
        "*Daily Updates:*\n"
        "▫️ */subscribe* - Get daily song picks\n"
        "▫️ */unsubscribe* - Stop daily updates\n\n"
        "*Pro Tips:* 💡\n"
        "• Always use a dash (-) between artist and song\n"
        "• Check spelling of artist and song names\n"
        "• For downloads, use short videos (under 50MB)\n\n"
        "Ready to explore? Try any command! 🚀"
    )

    try:
        update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}")
        # Fallback to plain text if markdown fails
        update.message.reply_text(
            help_text.replace('*', '').replace('▫️', '•'),
            disable_web_page_preview=True
        )


def quiz_command(update: Update, context: CallbackContext):
    """Handle the /quiz command to start a lyrics quiz."""
    user_id = update.effective_user.id
    try:
        logger.debug(f"Starting quiz for user {user_id}")
        quiz_data = start_quiz(user_id, mode="multiple_choice")
        if not quiz_data:
            update.message.reply_text(
                "😓 Oops! I couldn't start the quiz right now.\n"
                "Please try again in a moment! 🔄"
            )
            return

        current_question = quiz_data["current_question"]
        snippet = current_question["snippet"]
        options = current_question["options"]

        response = (
            "🎵 Welcome to the Multiple Choice Lyrics Quiz! 🎮\n\n"
            "I'll show you some lyrics, and you choose the correct song!\n"
            "Reply with A, B, C, or D to make your choice.\n\n"
            "Here's your first lyrics snippet:\n\n"
            f"{snippet}\n\n"
            "Which song is this? Choose from:\n\n"
            f"{format_multiple_choice_options(options)}\n\n"
            "Use /endquiz to finish the game early."
        )

        update.message.reply_text(response)
        logger.info(f"Successfully started quiz for user {user_id}")

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
        answer = update.message.text.strip().upper()
        logger.debug(f"Quiz answer received from user {user_id}: {answer}")

        # Immediate confirmation of receiving answer
        update.message.reply_text(f"📝 Received your answer: {answer}")

        if not answer or len(answer) != 1 or answer not in 'ABCD':
            logger.debug(f"Invalid quiz answer format: {answer}")
            return  # Not a valid quiz answer

        # Get the current quiz
        quiz_data = active_quizzes.get(user_id)
        if not quiz_data or quiz_data["state"] != "active":
            logger.debug(f"No active quiz found for user {user_id}")
            update.message.reply_text("No active quiz found! Start a new quiz with /quiz")
            return

        # Get the selected option
        options = quiz_data["current_question"]["options"]
        option_index = 'ABCD'.index(answer)
        if option_index >= len(options):
            logger.debug(f"Option index out of range: {option_index}")
            return

        selected_option = options[option_index]
        formatted_answer = f"{selected_option['artist']} - {selected_option['song']}"
        logger.debug(f"Selected answer: {formatted_answer}")

        is_correct, feedback = check_answer(user_id, formatted_answer)
        logger.debug(f"Answer check result - correct: {is_correct}, feedback: {feedback}")

        # Handle quiz completion
        if "Quiz completed!" in feedback:
            update.message.reply_text(f"{feedback}\n\n{end_quiz(user_id)}")
            return

        # Get current quiz data after answer check
        quiz_data = active_quizzes.get(user_id)
        if not quiz_data or quiz_data["state"] != "active":
            update.message.reply_text("Quiz session ended. Start a new quiz with /quiz!")
            return

        stats = get_quiz_stats(user_id)
        current_question = quiz_data["current_question"]
        snippet = current_question["snippet"]
        options = current_question["options"]

        response = (
            f"{feedback}\n\n"
            f"{stats}\n\n"
            "Here's your next lyrics snippet:\n\n"
            f"{snippet}\n\n"
            "Which song is this? Choose from:\n\n"
            f"{format_multiple_choice_options(options)}"
        )

        update.message.reply_text(response)
        logger.info(f"Successfully sent next question to user {user_id}")

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

        # Format header with song info and stats
        header = (
            f"🎵 {artist.strip()} - {song.strip()}\n\n"
            f"Song mood: {mood_emoji} {mood.title()}\n"
            f"Words: {stats['total_words']} | Lines: {stats['total_lines']} | "
            f"Vocabulary: {stats['vocabulary_richness']}%\n\n"
        )

        # Format and split lyrics into chunks
        formatted_lyrics = format_lyrics(lyrics)
        max_chunk_size = 3000  # Leave room for headers and formatting
        chunks = [formatted_lyrics[i:i + max_chunk_size] for i in range(0, len(formatted_lyrics), max_chunk_size)]

        # Send first message with header
        first_message = header + chunks[0]
        update.message.reply_text(first_message)

        # Send remaining chunks if any
        for i, chunk in enumerate(chunks[1:], 1):
            continuation_header = f"🎵 Continuation ({i+1}/{len(chunks)})...\n\n"
            update.message.reply_text(continuation_header + chunk)

        if len(chunks) > 1:
            update.message.reply_text(
                "Want more details? Try /stats with this song! 📊"
            )

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

        # First send a processing message
        processing_msg = update.message.reply_text(
            "🔄 Analyzing the song...\n"
            "This will take just a moment! 📊"
        )

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            processing_msg.edit_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Please check:\n"
                "• The spelling of the artist and song\n"
                "• If the song exists\n"
                "• Try another song from the same artist\n\n"
                "Need help? Use /help to see examples! 🔍"
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

        # Update the processing message with results
        processing_msg.edit_text(response)
        logger.info(f"Successfully sent stats to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing stats command for user {user_id}: {str(e)}")
        error_message = (
            "😓 Oops! Something went wrong while analyzing the song.\n"
            "Please try:\n"
            "• Check the spelling of artist and song\n"
            "• Wait a few moments and try again\n"
            "• Try a different song\n\n"
            "Example: /stats Ed Sheeran - Perfect 🎵"
        )
        try:
            update.message.reply_text(error_message)
        except Exception:
            # If the original message failed, try sending a new one
            update.message.reply_text(
                "😓 Something went wrong. Please try again in a moment! 🔄"
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


def analyze_command(update: Update, context: CallbackContext):
    """Handle the /analyze command for detailed song analysis."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query or "-" not in query:
            logger.info(f"User {user_id} provided invalid analysis query format")
            update.message.reply_text(
                "⚠️ Please use this format: /analyze artist - song\n"
                "For example: /analyze Eminem - Lose Yourself\n\n"
                "I'll give you a detailed analysis of the song! 📊"
            )
            return

        artist, song = query.split("-", 1)
        logger.info(f"User {user_id} requested analysis for '{artist.strip()} - {song.strip()}'")

        # Send typing action while processing
        update.message.chat.send_action(action="typing")

        lyrics = get_song_lyrics(artist.strip(), song.strip())
        if not lyrics:
            logger.info(f"No lyrics found for '{artist.strip()} - {song.strip()}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Please check the spelling and try again! 🔍"
            )
            return

        # Get detailed analysis
        analysis = get_detailed_song_analysis(lyrics)
        formatted_analysis = format_detailed_analysis(analysis)

        # Format response with song info
        response = (
            f"🎵 Detailed Analysis: {artist.strip()} - {song.strip()}\n\n"
            f"{formatted_analysis}"
        )

        update.message.reply_text(response)
        logger.info(f"Successfully sent analysis to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing analyze command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while analyzing the song.\n"
            "Please try again in a moment! 🔄"
        )


def download_command(update: Update, context: CallbackContext):
    """Handle the /download command."""
    user_id = update.effective_user.id
    try:
        # Get URL from command arguments
        if not context.args:
            logger.info(f"User {user_id} provided no URL for download")
            update.message.reply_text(
                "⚠️ Please provide a YouTube video URL!\n\n"
                "Use this format: /download video_url\n"
                "For example: /download https://www.youtube.com/watch?v=example"
            )
            return

        url = context.args[0]
        logger.info(f"User {user_id} requested download of: {url}")

        # Send processing message
        processing_message = update.message.reply_text(
            "🎬 Processing your download request...\n"
            "This might take a moment! ⏳"
        )

        # Download video
        success, result = download_youtube_video(url)

        if success:
            file_path, info_message = result

            # Update processing message with file info
            processing_message.edit_text(info_message)

            # Send video file
            with open(file_path, 'rb') as video_file:
                update.message.reply_video(
                    video_file,
                    caption="🎉 Enjoy your video! /help for more commands",
                    supports_streaming=True
                )

            # Cleanup
            cleanup_video(file_path)

        else:
            # Update processing message with error
            processing_message.edit_text(result)

    except Exception as e:
        logger.error(f"Error in download command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the download.\n"
            "Please try again later! 🔄"
        )


def format_multiple_choice_options(options):
    """Helper function to format multiple choice options neatly."""
    option_strings = []
    for i, option in enumerate(options):
        option_strings.append(f"{chr(65 + i)}. {option['artist']} - {option['song']}")
    return "\n".join(option_strings)


def wiki_command(update: Update, context: CallbackContext) -> None:
    """Handle the /wiki command."""
    user_id = update.effective_user.id

    try:
        query = " ".join(context.args)
        if not query:
            logger.info(f"User {user_id} provided no name for wiki search")
            update.message.reply_text(
                "⚠️ Please provide a name to search!\n\n"
                "Use this format: /wiki person name\n"
                "For example: /wiki Adele\n\n"
                "Give it a try! 🔍"
            )
            return

        logger.info(f"User {user_id} requested Wikipedia info for '{query}'")

        # Send "typing" action while processing
        update.message.chat.send_action(chat_action="typing")

        # Get Wikipedia information
        wiki_info = get_wikipedia_info(query)

        if not wiki_info:
            update.message.reply_text(
                "😕 Sorry, I couldn't find that person on Wikipedia.\n\n"
                "Please try:\n"
                "• Check the spelling of the name\n"
                "• Use the full name\n"
                "• Try a more specific search term\n\n"
                "Example: /wiki Taylor Swift 🔍"
            )
            return

        # Format and send response
        response = (
            f"📚 {wiki_info['title']}\n\n"
            f"{wiki_info['extract']}\n\n"
            f"🔗 Read more: {wiki_info['link']}\n\n"
            "Want to learn about someone else? Just use /wiki again! 🤓"
        )

        update.message.reply_text(
            response,
            disable_web_page_preview=True,
            parse_mode=None  # Ensure no parsing issues with special characters
        )
        logger.info(f"Successfully sent Wikipedia info to user {user_id}")

    except Exception as e:
        logger.error(f"Error in wiki command for user {user_id}: {str(e)}", exc_info=True)
        update.message.reply_text(
            "😓 Oops! Something went wrong while searching Wikipedia.\n"
            "Please try again in a moment! 🔄"
        )


def main():
    """Initialize bot handlers and start the bot."""
    token = os.environ.get('TELEGRAM_TOKEN')
    if not token:
        logger.error("TELEGRAM_TOKEN not found in environment variables")
        return

    try:
        updater = Updater(token=token, use_context=True)
        dp = updater.dispatcher

        # Add command handlers
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(CommandHandler("lyrics", lyrics_command))
        dp.add_handler(CommandHandler("stats", stats_command))
        dp.add_handler(CommandHandler("recommend", recommend_command))
        dp.add_handler(CommandHandler("quiz", quiz_command))
        dp.add_handler(CommandHandler("endquiz", end_quiz_command))
        dp.add_handler(CommandHandler("translate", translate_lyrics_command))
        dp.add_handler(CommandHandler("youtube", youtube_command))
        dp.add_handler(CommandHandler("analyze", analyze_command))
        dp.add_handler(CommandHandler("subscribe", subscribe_daily_command))
        dp.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
        dp.add_handler(CommandHandler("download", download_command))
        dp.add_handler(CommandHandler("wiki", wiki_command))

        # Add message handler for quiz answers
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, quiz_answer))

        # Register commands in the menu
        commands = [
            BotCommand("start", "Start the bot 👋"),
            BotCommand("help", "Show all commands and how to use them ℹ️"),
            BotCommand("lyrics", "Get song lyrics 🎵 (format: artist - song)"),
            BotCommand("stats", "Get song statistics 📊 (format: artist - song)"),
            BotCommand("recommend", "Get song recommendations 🎵 (format: artist - song)"),
            BotCommand("quiz", "Start a lyrics quiz game 🎮"),
            BotCommand("endquiz", "End the current quiz game"),
            BotCommand("translate", "Get Arabic translation of lyrics 🌍 (format: artist - song)"),
            BotCommand("subscribe", "Subscribe to daily song discovery 🎶"),
            BotCommand("unsubscribe", "Unsubscribe from daily song discovery 👋"),
            BotCommand("youtube", "Get YouTube link for song 🎬 (format: artist - song)"),
            BotCommand("analyze", "Get detailed song analysis 📊 (format: artist - song)"),
            BotCommand("download", "Download YouTube video 🎬 (format: /download video_url)"),
            BotCommand("wiki", "Get Wikipedia info about artists 📚 (format: /wiki name)")
        ]

        updater.bot.set_my_commands(commands)

        # Start the bot
        updater.start_polling()
        logger.info("Bot started successfully")

    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()