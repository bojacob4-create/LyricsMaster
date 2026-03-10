import logging
import os
from telegram import Update, BotCommand
from telegram.ext import CallbackContext, MessageHandler, Filters, CommandHandler
from telegram.error import TelegramError
from services.lyrics_service import get_song_lyrics
from services.translator_service import translate_to_arabic
from services.recommendation_service import get_similar_songs, format_recommendations
from services.quiz_service import (
    start_quiz, check_answer, get_quiz_stats, end_quiz,
    format_multiple_choice_options, format_quiz_question, active_quizzes
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
from services.youtube_downloader_service import download_youtube_video, cleanup_video
from services.ai_info_service import get_person_info
from input_parser import parse_song_query, search_lyrics_with_fallback, clean_input

logger = logging.getLogger(__name__)

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")

    user_first_name = update.effective_user.first_name
    welcome_message = (
        f"🎵 *Welcome, {user_first_name}!* 🎸\n\n"
        "I'm Lyrics Master — your personal music companion.\n\n"
        "*What I can do:*\n\n"
        "🎤 */lyrics* — Song lyrics with mood analysis\n"
        "📊 */stats* — Word counts and patterns\n"
        "🎵 */recommend* — Discover similar songs\n"
        "🔍 */analyze* — Deep lyrical breakdown\n"
        "🌍 */translate* — Arabic translation\n"
        "🎬 */youtube* — Find the music video\n"
        "📥 */download* — Download YouTube videos\n"
        "🎮 */quiz* — Lyrics guessing game\n"
        "📚 */wiki* — Artist info from Wikipedia\n"
        "🔔 */subscribe* — Daily song picks\n\n"
        "*Try it now:*\n"
        "• /lyrics Tyla - Water\n"
        "• /lyrics Shape of You\n"
        "• /recommend Adele - Hello\n\n"
        "Type */help* for the full guide! 💫"
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
        "🎵 *Lyrics Master — Command Guide* 🎸\n\n"
        "*🎤 Lyrics & Analysis*\n"
        "▫️ */lyrics* — Get song lyrics\n"
        "▫️ */stats* — Word counts and patterns\n"
        "▫️ */analyze* — Full lyrical breakdown\n"
        "▫️ */translate* — Arabic translation\n\n"
        "*🎵 Discovery*\n"
        "▫️ */recommend* — Find similar songs\n"
        "▫️ */youtube* — Find the music video\n"
        "▫️ */wiki* — Artist info from Wikipedia\n\n"
        "*🎮 Fun*\n"
        "▫️ */quiz* — Lyrics guessing game (40 songs!)\n"
        "▫️ */endquiz* — End current quiz\n\n"
        "*📥 Media*\n"
        "▫️ */download* — Download YouTube videos\n\n"
        "*🔔 Daily Updates*\n"
        "▫️ */subscribe* — Get daily song picks\n"
        "▫️ */unsubscribe* — Stop daily updates\n\n"
        "*💡 How to use song commands:*\n"
        "You can use any of these formats:\n"
        "• /lyrics Tyla - Water\n"
        "• /lyrics Water Tyla\n"
        "• /lyrics Water\n\n"
        "No strict format required — I'll figure it out! 🚀"
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
                "😓 Couldn't start the quiz right now.\n"
                "Please try again in a moment! 🔄"
            )
            return

        response = (
            "🎮 Lyrics Quiz — Let's Go!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "I'll show you lyrics from famous songs.\n"
            "Reply with A, B, C, or D to guess the song.\n"
            "Use /endquiz to finish early.\n\n"
        )
        response += format_quiz_question(quiz_data["current_question"], quiz_data)

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

        if not answer or len(answer) != 1 or answer not in 'ABCD':
            return

        quiz_data = active_quizzes.get(user_id)
        if not quiz_data or quiz_data["state"] != "active":
            return

        logger.debug(f"Quiz answer from user {user_id}: {answer}")

        is_correct, feedback = check_answer(user_id, answer)

        update.message.reply_text(feedback)
        logger.info(f"Quiz answer processed for user {user_id}: correct={is_correct}")

    except Exception as e:
        logger.error(f"Error processing quiz answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong processing your answer.\n"
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
        logger.info(f"User {user_id} raw lyrics input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song you're looking for!\n\n"
                "You can use any of these formats:\n"
                "• /lyrics Tyla - Water\n"
                "• /lyrics Water Tyla\n"
                "• /lyrics Water\n\n"
                "Give it a try! 🎵"
            )
            return

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for user {user_id}, query: '{query}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find those lyrics.\n\n"
                "Try different formats:\n"
                "• /lyrics Water\n"
                "• /lyrics Water Tyla\n"
                "• /lyrics Tyla - Water\n\n"
                "Tips:\n"
                "• Check the spelling\n"
                "• Try just the song name\n"
                "• Use the artist's most known name\n\n"
                "Need help? Use /help for more examples! 💡"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)
        logger.info(f"Found lyrics for user {user_id}: '{display_title}'")

        mood = detect_song_mood(lyrics)
        stats = get_song_statistics(lyrics)

        mood_emoji = {
            'happy': '😊',
            'sad': '😢',
            'romantic': '💖',
            'energetic': '⚡',
            'relaxed': '😌'
        }.get(mood, '🎵')

        header = (
            f"🎵 {display_title}\n\n"
            f"Song mood: {mood_emoji} {mood.title()}\n"
            f"Words: {stats['total_words']} | Lines: {stats['total_lines']} | "
            f"Vocabulary: {stats['vocabulary_richness']}%\n\n"
        )

        formatted_lyrics = format_lyrics(lyrics)
        max_chunk_size = 3000
        chunks = [formatted_lyrics[i:i + max_chunk_size] for i in range(0, len(formatted_lyrics), max_chunk_size)]

        first_message = header + chunks[0]
        update.message.reply_text(first_message)

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
        logger.info(f"User {user_id} raw stats input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song to analyze!\n\n"
                "Examples:\n"
                "• /stats Ed Sheeran - Perfect\n"
                "• /stats Perfect Ed Sheeran\n"
                "• /stats Perfect\n\n"
                "Give it another try! 📊"
            )
            return

        update.message.chat.send_action(action="typing")

        processing_msg = update.message.reply_text(
            "🔄 Analyzing the song...\n"
            "This will take just a moment! 📊"
        )

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for stats, query: '{query}'")
            processing_msg.edit_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Try different formats:\n"
                "• /stats Perfect\n"
                "• /stats Perfect Ed Sheeran\n"
                "• /stats Ed Sheeran - Perfect\n\n"
                "Need help? Use /help to see examples! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)
        stats = get_song_statistics(lyrics)
        formatted_stats = format_statistics(stats)

        response = (
            f"🎵 {display_title}\n\n"
            f"{formatted_stats}\n\n"
            "Want to see the lyrics? Try /lyrics with this song! 🎤"
        )

        processing_msg.edit_text(response)
        logger.info(f"Successfully sent stats to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing stats command for user {user_id}: {str(e)}")
        try:
            update.message.reply_text(
                "😓 Oops! Something went wrong while analyzing the song.\n"
                "Please try again in a moment! 🔄"
            )
        except Exception:
            pass


def recommend_command(update: Update, context: CallbackContext):
    """Handle the /recommend command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        logger.info(f"User {user_id} raw recommend input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song to base recommendations on!\n\n"
                "Examples:\n"
                "• /recommend Taylor Swift - Love Story\n"
                "• /recommend Love Story Taylor Swift\n"
                "• /recommend Love Story\n\n"
                "Give it another try! 🎵"
            )
            return

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for recommendations, query: '{query}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Try different formats:\n"
                "• /recommend Love Story\n"
                "• /recommend Taylor Swift - Love Story\n\n"
                "Check the spelling and try again! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)
        mood = detect_song_mood(lyrics)
        use_artist = artist if artist else query
        use_song = song if song else query
        recommendations = get_similar_songs(use_artist, use_song, mood)
        formatted_recommendations = format_recommendations(recommendations, display_title)

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
        logger.info(f"User {user_id} raw translate input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song to translate!\n\n"
                "Examples:\n"
                "• /translate Adele - Hello\n"
                "• /translate Hello Adele\n"
                "• /translate Hello\n\n"
                "Let's try again! 🎵"
            )
            return

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for translation, query: '{query}'")
            update.message.reply_text(
                "😕 I couldn't find the lyrics for this song, so I can't translate it.\n\n"
                "Try different formats:\n"
                "• /translate Hello\n"
                "• /translate Adele - Hello\n\n"
                "Check the spelling and try again! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)

        processing_msg = update.message.reply_text(
            f"✅ Found lyrics for {display_title}!\n"
            "🔄 Translating to Arabic... Please wait! ✨"
        )

        translated_lyrics = translate_to_arabic(lyrics)
        if translated_lyrics:
            formatted_lyrics = format_lyrics(translated_lyrics)
            response = (
                f"🎵 {display_title}\n"
                f"🌍 Arabic Translation:\n\n"
                f"{formatted_lyrics}"
            )
            processing_msg.edit_text(response)
            logger.info(f"Successfully sent translated lyrics to user {user_id}")
        else:
            logger.warning(f"Translation failed for user {user_id}")
            processing_msg.edit_text(
                "😓 I found the lyrics but the translation service is unavailable right now.\n"
                "Please try again in a few moments! 🧞‍♂️\n\n"
                f"In the meantime, try /lyrics {query} to see the original lyrics!"
            )

    except Exception as e:
        logger.error(f"Error processing translate command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "🤖 Oops! Something went wrong with the translation.\n"
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
                "🔔 You're subscribed!\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Every day you'll get a curated song with:\n"
                "• Full lyrics and mood analysis\n"
                "• Word statistics and patterns\n"
                "• A fresh discovery to explore\n\n"
                "Your first pick arrives tomorrow! 🎶\n\n"
                "To stop: /unsubscribe"
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
                "👋 Unsubscribed from daily songs.\n\n"
                "You can re-subscribe anytime with /subscribe 🎵"
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
        logger.info(f"User {user_id} raw youtube input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song to find on YouTube!\n\n"
                "Examples:\n"
                "• /youtube Ed Sheeran - Perfect\n"
                "• /youtube Perfect Ed Sheeran\n"
                "• /youtube Perfect\n\n"
                "Let's try again! 🎵"
            )
            return

        update.message.chat.send_action(action="typing")

        candidates = parse_song_query(query)
        url = None
        used_artist = ''
        used_song = ''

        for artist, song in candidates:
            if not artist and not song:
                continue
            a = artist if artist else song
            s = song if artist else ''
            logger.info(f"YouTube search trying: artist='{a}', song='{s}'")
            result = get_youtube_link(a, s)
            if result:
                url = result
                used_artist = a
                used_song = s
                break

        if not url:
            url = get_youtube_link(query, '')
            used_artist = query
            used_song = ''

        if not url:
            update.message.reply_text(
                "😕 Sorry, I couldn't find this song on YouTube.\n\n"
                "Try different formats:\n"
                "• /youtube Perfect\n"
                "• /youtube Ed Sheeran - Perfect\n\n"
                "Check the spelling and try again! 🔄"
            )
            return

        display_artist = used_artist
        display_song = used_song if used_song else used_artist
        response = format_youtube_response(display_artist, display_song, url)
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
        logger.info(f"User {user_id} raw analyze input: '{query}'")

        if not query:
            update.message.reply_text(
                "⚠️ Please tell me what song to analyze!\n\n"
                "Examples:\n"
                "• /analyze Eminem - Lose Yourself\n"
                "• /analyze Lose Yourself Eminem\n"
                "• /analyze Lose Yourself\n\n"
                "I'll give you a detailed analysis! 📊"
            )
            return

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for analysis, query: '{query}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Try different formats:\n"
                "• /analyze Lose Yourself\n"
                "• /analyze Eminem - Lose Yourself\n\n"
                "Check the spelling and try again! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)

        analysis = get_detailed_song_analysis(lyrics)
        formatted_analysis = format_detailed_analysis(analysis)

        response = (
            f"🎵 Detailed Analysis: {display_title}\n\n"
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
                "📥 Download a YouTube Video\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Usage: /download [YouTube URL]\n\n"
                "Supported formats:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/...\n\n"
                "⚠️ Max file size: 50MB\n"
                "⚠️ Some videos may be restricted"
            )
            return

        url = context.args[0]
        logger.info(f"User {user_id} requested download of: {url}")

        processing_message = update.message.reply_text(
            "📥 Downloading...\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⏳ Fetching video info and preparing download.\n"
            "This may take 30–60 seconds."
        )

        success, result = download_youtube_video(url)

        if success:
            file_path, info_message = result
            processing_message.edit_text(info_message)

            try:
                with open(file_path, 'rb') as video_file:
                    update.message.reply_video(
                        video_file,
                        caption="🎉 Here's your video!",
                        supports_streaming=True
                    )
            except Exception as send_err:
                logger.error(f"Failed to send video: {send_err}")
                processing_message.edit_text(
                    "❌ The video downloaded but was too large to send via Telegram.\n"
                    "Telegram limit is 50MB. Try a shorter video."
                )

            cleanup_video(file_path)

        else:
            processing_message.edit_text(result)

    except Exception as e:
        logger.error(f"Error in download command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the download.\n"
            "Please try again later! 🔄"
        )


def wiki_command(update: Update, context: CallbackContext) -> None:
    """Handle the /wiki command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query:
            logger.info(f"User {user_id} provided no query")
            update.message.reply_text(
                "⚠️ Please provide an artist name!\n\n"
                "Use this format: /wiki artist name\n"
                "For example: /wiki Taylor Swift\n\n"
                "Give it a try! 🎵"
            )
            return

        logger.info(f"User {user_id} requested info for '{query}'")

        # Send initial processing message
        processing_msg = update.message.reply_text(
            "🎵 Let me tell you about this artist...\n"
            "Just a moment! ✨"
        )

        # Get generated information
        person_info = get_person_info(query)

        if not person_info:
            processing_msg.edit_text(
                "😕 I couldn't gather information about this artist.\n\n"
                "Please try:\n"
                "• Check if the name is spelled correctly\n"
                "• Use their full artist name\n"
                "• Try again in a moment\n\n"
                "Example: /wiki Taylor Swift 🎵"
            )
            return

        response = (
            f"📚 *{person_info['title']}*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{person_info['info']}"
        )

        try:
            # Try sending with markdown
            processing_msg.edit_text(
                response,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except TelegramError:
            # If markdown fails, send without formatting
            processing_msg.edit_text(
                response.replace('*', ''),
                disable_web_page_preview=True
            )

        logger.info(f"Successfully sent artist info to user {user_id}")

    except TelegramError as e:
        logger.error(f"Telegram error for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong sending the message.\n"
            "Please try again in a moment! 🔄"
        )
    except Exception as e:
        logger.error(f"Error in wiki command for user {user_id}: {str(e)}", exc_info=True)
        error_message = (
            "😓 I couldn't process that request right now.\n"
            "Please try again in a few moments! 🔄"
        )
        if 'processing_msg' in locals():
            processing_msg.edit_text(error_message)
        else:
            update.message.reply_text(error_message)

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
            BotCommand("start", "Welcome & overview"),
            BotCommand("help", "Full command guide"),
            BotCommand("lyrics", "🎤 Get song lyrics"),
            BotCommand("stats", "📊 Song word statistics"),
            BotCommand("recommend", "🎵 Find similar songs"),
            BotCommand("analyze", "🔍 Deep lyrical analysis"),
            BotCommand("translate", "🌍 Arabic translation"),
            BotCommand("youtube", "🎬 Find the music video"),
            BotCommand("download", "📥 Download YouTube video"),
            BotCommand("quiz", "🎮 Lyrics guessing game"),
            BotCommand("endquiz", "End current quiz"),
            BotCommand("wiki", "📚 Artist info from Wikipedia"),
            BotCommand("subscribe", "🔔 Daily song picks"),
            BotCommand("unsubscribe", "Stop daily updates"),
        ]

        updater.bot.set_my_commands(commands)

        # Start the bot
        updater.start_polling()
        logger.info("Bot started successfully")

    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()