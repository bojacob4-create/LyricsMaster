import logging
import os
import re
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, MessageHandler, Filters, CommandHandler
from telegram.error import TelegramError, Unauthorized
from buttons import (
    lyrics_buttons, song_dashboard_buttons, artist_buttons, artist_summary_buttons,
    recommend_buttons, song_list_buttons, ambiguous_buttons,
    analyze_buttons, stats_buttons, artist_analyze_buttons, recommend_pick_buttons,
    daily_song_buttons, subscribe_count_buttons, emoji_exit_buttons,
    recommend_results_buttons, daily_picker_buttons
)
from services.lyrics_service import get_song_lyrics, canonicalize_track_names
from services.translator_service import (
    translate_to_arabic, translate_text, get_language_code,
    get_language_display, get_supported_languages_text
)
from services.recommendation_service import get_similar_songs, get_similar_songs_fresh, format_recommendations
from services.quiz_service import (
    start_quiz, check_answer, get_quiz_stats, end_quiz,
    format_multiple_choice_options, format_quiz_question, active_quizzes
)
from services.daily_song_service import (
    subscribe_user,
    unsubscribe_user,
    get_daily_song,
    format_daily_song,
    get_subscribed_users,
    get_subscriber_data,
)
from utils import (
    format_lyrics,
    detect_song_mood,
    get_song_statistics,
    format_statistics,
    get_detailed_song_analysis,
    format_detailed_analysis,
    detect_themes,
    escape_markdown as md,
)
from services.youtube_service import get_youtube_link, format_youtube_response
from services.youtube_downloader_service import download_youtube_video, download_youtube_audio, download_audio_for_song, cleanup_video, note_mp3_file_id, forget_mp3_file_id, is_cached_mp3_path
from services.ai_info_service import get_person_info
from services.artist_service import (
    get_artist_info, format_artist_info, get_trending_songs, format_trending,
    get_top_by_genre, format_top_songs, get_available_genres, get_random_song
)
from input_parser import parse_song_query, search_lyrics_with_fallback, clean_input
from intent_router import detect_intent

# ── Round 4: discovery + fun services ─────────────────────────────────────
from services.discovery_service import (
    MOOD_BUTTONS, normalize_mood, get_mood_mix,
    parse_extend_lines, get_recent_picks, blend_vibe, get_extend_recs,
    interpret_theme, match_theme,
    DECADE_POOLS, normalize_decade, get_throwback,
    get_new_music,
)
from services.fun_service import (
    create_duel, join_duel, get_duel_questions,
    record_duel_answer, duel_standings, delete_duel,
    get_daily_status, record_daily_play, make_daily_questions,
    get_emoji_puzzle, check_emoji_guess,
    log_interaction, get_music_stats,
    BADGES, award_badge, get_user_badges, auto_award_from_stats,
)
from services.quiz_service import _correct_display
from services.recommendation_service import _detect_genre_fast
from buttons import mood_buttons, decade_buttons

logger = logging.getLogger(__name__)

# ── Round 4: per-user session state (in-memory; games are live sessions) ────
_pending_extend = {}        # user_id -> True while waiting for song list
active_emoji = {}           # user_id -> {'puzzle', 'score', 'played'}
active_duel_sessions = {}   # user_id -> {'code','idx','score','chat_id','name'}
active_daily = {}           # user_id -> {'questions','idx','score'}
_duel_chat_ids = {}         # code -> {str(user_id): chat_id} for result delivery


def _safe_genre(artist_name: str) -> str:
    """Local genre lookup — never network, never raises."""
    try:
        return _detect_genre_fast(artist_name or '')
    except Exception:
        return 'pop'


def _new_badge_lines(user_id: int) -> list:
    """Award stat-based badges; return Markdown congrats lines for new ones."""
    lines = []
    try:
        for bid in auto_award_from_stats(user_id):
            b = BADGES.get(bid, {})
            lines.append(
                f"🏅 New badge: {b.get('emoji', '🎖️')} "
                f"*{b.get('name', bid)}* — {b.get('desc', '')}"
            )
    except Exception as e:
        logger.debug(f"badge auto-award failed: {e}")
    return lines


def _award_badge_line(user_id: int, badge_id: str) -> str:
    """Award one badge; return a Markdown congrats line or ''."""
    try:
        if award_badge(user_id, badge_id):
            b = BADGES.get(badge_id, {})
            return (
                f"\n\n🏅 New badge: {b.get('emoji', '🎖️')} "
                f"*{b.get('name', badge_id)}* — {b.get('desc', '')}"
            )
    except Exception as e:
        logger.debug(f"badge award failed: {e}")
    return ""

def start_command(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")

    user_first_name = update.effective_user.first_name
    welcome_message = (
        f"🎵 *Welcome, {user_first_name}!* 🎸\n\n"
        "I'm Lyrics Master — your personal music companion.\n\n"
        "*What I can do:*\n\n"
        "🎵 */song* — Full song dashboard\n"
        "🎤 */lyrics* — Song lyrics with mood\n"
        "📊 */stats* — Word counts and patterns\n"
        "🎵 */recommend* — Discover similar songs\n"
        "🎧 */mood* — A mix for your mood\n"
        "🎶 */extend* — Finish my playlist\n"
        "🔍 */analyze* — Deep lyrical breakdown\n"
        "🎤 */artist* — Quick artist profile\n"
        "🔝 */top* — Top songs by genre\n"
        "🎲 */random [genre]* — Random song discovery\n"
        "🎬 */youtube* — Find the music video\n"
        "🎮 */quiz* — Lyrics guessing game\n"
        "⚔️ */duel* — Quiz duel with a friend\n"
        "🎯 */daily* — Daily challenge\n"
        "🔔 */subscribe* — Daily song picks\n\n"
        "*Try it now:*\n"
        "• /song OneRepublic - Counting Stars\n"
        "• /lyrics The Weeknd - Blinding Lights\n"
        "• /top pop\n"
        "• /random\n\n"
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
        "*🎵 All-in-One*\n"
        "▫️ */song* — Full song dashboard\n"
        "▫️ */random [genre]* — Random song discovery\n\n"
        "*🎤 Lyrics & Analysis*\n"
        "▫️ */lyrics* — Get song lyrics\n"
        "▫️ */stats* — Word counts and patterns\n"
        "▫️ */analyze* — Full lyrical breakdown\n"
        "▫️ */translate* — Translate lyrics to any language\n\n"
        "*🎵 Discovery*\n"
        "▫️ */recommend* — Find similar songs\n"
        "▫️ */mood* — A mix for your mood 🎧\n"
        "▫️ */extend* — Finish my playlist (give me 3 songs)\n"
        "▫️ */about* — Find songs by theme or meaning 💭\n"
        "▫️ */throwback* — 80s / 90s / 2000s / 2010s gems 🕺\n"
        "▫️ */newmusic* — What's hot right now 🔥\n"
        "▫️ */top* — Top songs by genre\n"
        "▫️ */artist* — Quick artist profile\n"
        "▫️ */youtube* — Find the music video\n"
        "▫️ */wiki* — Artist Wikipedia info\n"
        "▫️ */trending* — Trending songs now\n\n"
        "*🎮 Fun*\n"
        "▫️ */quiz* — Lyrics guessing game (110+ songs, 3 game modes!)\n"
        "▫️ */endquiz* — End current quiz\n"
        "▫️ */duel* — Quiz duel with a friend ⚔️\n"
        "▫️ */daily* — Daily 5-question challenge 🎯\n"
        "▫️ */emoji* — Guess the song from emojis 🎭\n"
        "▫️ */mystats* — Your music personality 🎧\n"
        "▫️ */badges* — Your achievements 🏅\n\n"
        "*🔔 Daily Updates*\n"
        "▫️ */subscribe* — Get daily song picks\n"
        "▫️ */unsubscribe* — Stop daily updates\n\n"
        "*💡 How to use:*\n"
        "• /song Adele - Hello\n"
        "• /lyrics The Weeknd - Blinding Lights\n"
        "• /recommend Bad Bunny - Tití Me Preguntó\n"
        "• /top pop\n"
        "• /random\n\n"
        "Use *Artist - Song* format for best results! 🚀"
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


# ── Unknown commands (round 6 QA) ───────────────────────────────────────────
# Without this, a fat-fingered "/strt" hits no CommandHandler and the text
# handler explicitly excludes commands → total silence, the bot looks dead.
_KNOWN_COMMANDS = [
    'start', 'help', 'song', 'lyrics', 'recommend', 'artist', 'youtube',
    'translate', 'analyze', 'stats', 'top', 'trending', 'random', 'quiz',
    'endquiz', 'throwback', 'mood', 'decade', 'mp3', 'download',
    'subscribe', 'unsubscribe', 'daily', 'duel', 'emoji', 'mystats',
    'badges', 'wiki', 'about', 'newmusic', 'extend', 'cancel',
]


def unknown_command_handler(update: Update, context: CallbackContext):
    """Catch-all for mistyped commands: 'Did you mean /start?'"""
    import difflib
    try:
        text = (update.message.text or '').strip()
        cmd = text.split()[0].lstrip('/').split('@')[0].lower() if text else ''
        matches = difflib.get_close_matches(cmd, _KNOWN_COMMANDS, n=1, cutoff=0.6)
        if matches:
            update.message.reply_text(
                f"🤔 Did you mean /{matches[0]}?\n\n"
                "Type /help to see everything I can do."
            )
        else:
            update.message.reply_text(
                "🤔 I don't know that command.\n\n"
                "Type /help to see everything I can do."
            )
    except Exception as e:
        logger.warning(f"unknown_command_handler error: {e}")


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

        # Round 4: stats + first-quiz badge
        try:
            log_interaction(user_id, 'quiz_start')
            response += _award_badge_line(user_id, 'first_quiz')
        except Exception as _e:
            logger.debug(f"round4 quiz hook failed: {_e}")

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

        # Round 4: track correct answers + milestone badges (local only)
        try:
            if is_correct:
                log_interaction(user_id, 'quiz_correct')
            for _bl in _new_badge_lines(user_id):
                feedback += f"\n{_bl}"
        except Exception as _e:
            logger.debug(f"round4 quiz hook failed: {_e}")

        update.message.reply_text(feedback)
        logger.info(f"Quiz answer processed for user {user_id}: correct={is_correct}")

    except Exception as e:
        logger.error(f"Error processing quiz answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong processing your answer.\n"
            "Try /quiz to start a new game! 🔄"
        )


_pending_recommend_artist = {}
# Values are dicts: {'artist': str, 'query': str} where 'query' is the
# original user input that led to the artist question (needed so an artist
# correction from the user can be matched back to the song they meant).

# Tracks artists already shown per (user, seed song) so the "More like this"
# button can serve fresh picks: {(user_id, seed_lower): [artist_lower, ...]}.
_shown_recs = {}

# Stores dominant-match confirmation waiting for user's "yes/no" reply.
# Structure: {user_id: {'artist': str, 'song': str, 'intent_cmd': str}}
_pending_confirmation: dict = {}

# Stores a just-sent multi-candidate disambiguation ("Which one did you
# mean?") so the user's NEXT message can be understood as a SELECTION:
# typing one of the artists (or a number 1-3) picks that candidate instead
# of starting a brand-new search.
# Structure: {user_id: {'candidates': [{'artist','song'}, ...], 'ts': float}}
# TTL: 5 minutes — a fresh message after that is a new request.
_pending_disambig: dict = {}
_DISAMBIG_TTL = 300

# Pending "Translate to…" answers.  Two flows share it:
#   (a) user tapped 🌐 Translate to… on a song card → query set, lang None
#       → the next message is the LANGUAGE name.
#   (b) user typed "Translate to Spanish" with no song named → lang set,
#       query None → the next message is the SONG ("Artist - Song").
# An explicit new request (translate/lyrics/random/…) clears the pending
# answer and routes normally instead.  TTL: 5 minutes.
_pending_translate_lang: dict = {}
_TRANSLATE_TTL = 300

# Last song dashboard/lyrics shown per user — lets "Translate to Spanish"
# (no song named) apply to the song the user is currently viewing.
_last_song: dict = {}


def _names_match(a: str, b: str) -> bool:
    """Fuzzy artist-name equality: containment either way, case-insensitive."""
    a1, a2 = (a or '').lower().strip(), (b or '').lower().strip()
    return bool(a1) and bool(a2) and (a1 in a2 or a2 in a1)


def _query_matches_song(query: str, song: str) -> bool:
    """Check whether a song title matches the user's original query.

    Used when the user corrects a wrongly-guessed artist: the original
    query ("rush") should describe the found song ("Rush").
    """
    q, s = (query or '').lower().strip(), (song or '').lower().strip()
    if not q or not s:
        return False
    if q in s or s in q:
        return True
    qwords = [w for w in re.findall(r'[a-z0-9]+', q) if len(w) > 2]
    return bool(qwords) and all(w in s for w in qwords)


def _disambiguation_buttons(candidates) -> 'InlineKeyboardMarkup':
    """Tappable buttons for a 'Which one did you mean?' candidate list.

    The old UX printed `/song Artist - Song` in backticks, which is NOT
    tappable in Telegram — the user had to retype it.  One tap on a button
    now opens the song card directly (via the existing 'song' callback).
    """
    from buttons import _cb
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for c in (candidates or [])[:5]:
        label = f"🎵 {c['artist']} - {c['song']}"
        if len(label) > 60:
            label = label[:57] + "…"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=_cb("song", f"{c['artist']} - {c['song']}"))])
    return InlineKeyboardMarkup(rows)


def _remember_disambiguation(user_id: int, candidates) -> None:
    """Remember a just-sent candidate list for follow-up selection."""
    _pending_disambig[user_id] = {
        'candidates': list(candidates or [])[:5],
        'ts': time.time(),
    }


def _match_disambiguation_choice(text: str, candidates):
    """Match a follow-up message against a pending candidate list.

    Returns the chosen {'artist','song'} candidate, or None when the text
    is not a selection.  Accepts:
      • a number ("1", "2", …) — the position in the shown list;
      • an artist name ("Justin Bieber", even just "bieber");
      • a song title from the list.
    Matching is accent-insensitive and word-based (nlp_router._covers),
    so minor variations still select the intended candidate.
    """
    t = (text or '').strip()
    if not t or not candidates:
        return None
    if t.isdigit():
        idx = int(t) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
        return None
    # Guard: long sentences are new requests, never selections.
    if len(t.split()) > 6 or len(t) > 60:
        return None
    try:
        from services.nlp_router import _covers
    except Exception:
        return None
    for c in candidates:
        if _covers(t, c.get('artist', '')) or _covers(t, c.get('song', '')):
            return c
    return None


def _sole_artist_name(name, candidates):
    """Pure conflict-free check: is `name` best read as an artist's name?

    True only when ALL candidates are by ONE artist AND the input covers
    that artist's name (accent-insensitive).  "Ghost" -> artists {Ghost,
    Justin Bieber, ...} -> None.  "Blinding Lights" -> sole artist The
    Weeknd, but the input doesn't cover the artist name -> None.
    Never raises.
    """
    if not candidates:
        return None
    try:
        from services.nlp_router import _covers, _norm
    except Exception:
        return None
    artists = {_norm(c.get('artist', '')) for c in candidates}
    artists.discard('')
    if len(artists) == 1:
        sole = candidates[0]['artist']
        if _covers(name, sole):
            return sole
    return None


def _detect_bare_artist_name(name: str):
    """General bare-artist-name check - beyond the 43 local-DB artists.

    Typing just an artist's name ("Justin Bieber") should show the artist
    card, not song suggestions.  Delegates the decision to
    _sole_artist_name (conflict-free by design): "Ghost" (many artists)
    still falls through to song disambiguation exactly as before.

    Returns (canonical_artist_name_or_None, candidates).  Never raises.
    """
    try:
        from services.nlp_router import search_song_candidates
        cands = search_song_candidates(name) or []
        return _sole_artist_name(name, cands), cands
    except Exception:
        return None, []

_YES_WORDS = frozenset({
    'yes', 'yeah', 'yep', 'yup', 'sure', 'ok', 'okay', 'correct',
    "that's it", "that one", 'y', 'right', 'affirmative', 'definitely',
    'absolutely', 'exactly', 'of course', 'please', 'go ahead', 'do it',
    'confirm', 'that', "yes please", 'sounds good', 'perfect',
})
_NO_WORDS = frozenset({
    'no', 'nope', 'nah', 'wrong', 'cancel', 'nevermind', 'never mind',
    'different', 'neither', 'n', 'nah', 'not that', 'not this',
    'something else', 'other', 'others',
})

_AMBIGUOUS_NOISE = {'song', 'songs', 'music', 'track', 'tracks', 'video', 'audio', 'clip', 'artist'}

# Greetings are not song searches — "hello" must not become a Last.fm lookup
# for Adele's "Hello". Short-circuited before the bare-title fast path.
_GREETING_WORDS = frozenset({
    'hi', 'hello', 'hey', 'yo', 'hiya', 'howdy', 'sup', 'hola',
    'salam', 'salaam', 'marhaba', 'morning', 'evening', 'afternoon',
})

# Keywords that indicate the user has moved on to a new request (Step 3 guard).
# Defined at module level to avoid re-allocating on every message.
_INTENT_KEYWORDS = frozenset({
    'lyrics', 'lyric', 'analyze', 'analyse', 'recommend', 'recommendation',
    'play', 'find', 'give', 'search', 'similar', 'like', 'something',
    'translate', 'youtube', 'trending', 'chart', 'top', 'random',
    'by', 'from', 'want', 'need', 'show', 'get', 'tell', 'what',
})

def _clean_ambiguous_query(text: str) -> str:
    words = text.strip().split()
    cleaned = [w for w in words if w.lower() not in _AMBIGUOUS_NOISE]
    if not cleaned:
        return text.strip()
    result = ' '.join(cleaned)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


_local_song_titles_cache = None


def _local_song_titles() -> set:
    """Lowercase song titles from our local pools (quiz + random + genre tops).

    Used by the bare-artist-name step to spot names that are ALSO song
    titles (e.g. "rush"), so those keep the disambiguation prompt instead
    of jumping straight to an artist card.
    """
    global _local_song_titles_cache
    if _local_song_titles_cache is None:
        titles = set()
        try:
            from services.quiz_service import get_quiz_songs
            for s in get_quiz_songs():
                if isinstance(s, dict) and s.get('song'):
                    titles.add(s['song'].lower().strip())
        except Exception:
            pass
        try:
            from services.artist_service import RANDOM_SONGS_POOL, GENRE_TOP_SONGS
            for s in RANDOM_SONGS_POOL:
                if isinstance(s, dict) and s.get('song'):
                    titles.add(s['song'].lower().strip())
            for songs in GENRE_TOP_SONGS.values():
                for s in songs:
                    if isinstance(s, dict) and s.get('song'):
                        titles.add(s['song'].lower().strip())
        except Exception:
            pass
        _local_song_titles_cache = titles
    return _local_song_titles_cache


def _is_bare_title_fast_path(text: str) -> bool:
    """True when the message is a bare song title that should skip the NLP layer.

    Short inputs (<=3 words) with no intent keywords can never be resolved
    confidently by the OpenAI router — they always end at Last.fm
    disambiguation ("Did you mean X - Y?").  Skipping the API round-trip
    (~1-3s) reaches the identical result faster and costs nothing.
    """
    words = text.strip().split()
    if not words or len(words) > 3:
        return False
    if ' - ' in text or ' – ' in text or ' — ' in text:
        return False
    if any(w.lower().strip('.,!?') in _INTENT_KEYWORDS for w in words):
        return False
    # Need at least 2 alphabetic chars — "???" / "123" have no searchable content.
    return sum(1 for c in text if c.isalpha()) >= 2


def natural_language_handler(update: Update, context: CallbackContext):
    """Handle non-command text messages via intent detection."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    # ── Round 6 QA: input length cap ───────────────────────────────────────
    # Multi-thousand-character pastes must never reach provider APIs verbatim.
    if len(text) > 500:
        update.message.reply_text(
            "📝 That's a bit long for me to read as one message!\n\n"
            "Try a shorter song or artist name — like `Adele - Hello`.",
            parse_mode='Markdown',
        )
        return

    # ── Round 4a: pending /extend song list (multi-line "Artist - Title") ───
    # Must run before the regex router, which would otherwise treat the
    # lines as a new song request.
    if user_id in _pending_extend:
        _pending_extend.pop(user_id, None)
        _handle_extend_songs(update, user_id, text)
        return

    # ── Round 4b: emoji game guesses (free text, e.g. "Tyla - Water") ───────
    # Must run before the regex router for the same reason.
    # Guards (round 6 QA): the game must never permanently hijack input.
    #  - TTL: 10 min of inactivity auto-ends the game.
    #  - Explicit new requests (mp3/lyrics/recommend/…) end the game and
    #    fall through to normal routing instead of "❌ Not quite".
    if user_id in active_emoji:
        _sess = active_emoji.get(user_id) or {}
        if time.time() - _sess.get('last_active', 0) > 600:
            active_emoji.pop(user_id, None)
            update.message.reply_text(
                "🎭 The emoji game ended (10 minutes idle).\n"
                "Type /emoji anytime to play again! 🎶"
            )
            # Fall through — handle the current message normally.
        else:
            _sess['last_active'] = time.time()
            _intent_probe = None
            try:
                _intent_probe, _ = detect_intent(text)
            except Exception:
                pass
            # A bare "Artist - Title" guess routes as intent 'song' — that
            # stays in the game. Anything with an explicit intent keyword is
            # a new request: end the game, handle normally.
            if _intent_probe and _intent_probe not in ('song',):
                _score, _played = _sess.get('score', 0), _sess.get('played', 0)
                active_emoji.pop(user_id, None)
                update.message.reply_text(
                    f"🎭 Emoji game ended (score {_score}/{_played}). "
                    "On to your request! 👇"
                )
                # Fall through to normal routing below.
            else:
                _handle_emoji_guess(update, user_id, text)
                return

    # ── Pending "Translate to…" answer ───────────────────────────────────────
    # 🌐 Translate to… asked for a language; "Translate to Spanish" (no song)
    # asked for a song.  Resolve the missing piece from this message.
    # Runs before disambiguation + the regex router.  An explicit new
    # request (lyrics/random/…) clears the pending answer and routes
    # normally instead.
    _tp = _pending_translate_lang.get(user_id)
    if _tp:
        if time.time() - _tp.get('ts', 0) > _TRANSLATE_TTL:
            _pending_translate_lang.pop(user_id, None)
            _tp = None
        elif _tp.get('query') and not _tp.get('lang_code'):
            # Flow (a): the button asked for a LANGUAGE name.
            # Check for a language BEFORE the intent probe — language names
            # themselves ('spanish') trigger the translate intent.
            _t_lang_code, _t_lang_word = _extract_language_name(text)
            if _t_lang_code:
                _pending_translate_lang.pop(user_id, None)
                logger.info(
                    f"Translate-to follow-up for user {user_id}: "
                    f"'{text}' → {_t_lang_code} for '{_tp['query']}'"
                )
                context.args = f"{_tp['query']} to {_t_lang_word}".split()
                translate_lyrics_command(update, context)
                return
            _t_intent, _ = detect_intent(text)
            if _t_intent:
                # A new structured request — drop the pending answer and
                # route it normally.
                _pending_translate_lang.pop(user_id, None)
                _tp = None
            else:
                _pending_translate_lang.pop(user_id, None)
                supported = get_supported_languages_text()
                update.message.reply_text(
                    f"😕 I don't support \"{text}\" as a language.\n\n"
                    f"Supported languages: {supported}\n\n"
                    "Tap 🌐 Translate to… on a song card to try again! 🔄"
                )
                return
        elif _tp.get('lang_code') and not _tp.get('query'):
            # Flow (b): "Translate to Spanish" asked for a SONG.
            # A 'song'-looking reply ("Adele - Hello") IS the answer —
            # only a different explicit request reroutes.
            _t_intent, _ = detect_intent(text)
            if _t_intent and _t_intent != 'song':
                _pending_translate_lang.pop(user_id, None)
                _tp = None
            else:
                _pending_translate_lang.pop(user_id, None)
                logger.info(
                    f"Translate-song follow-up for user {user_id}: "
                    f"'{text}' → {_tp['lang_code']}"
                )
                context.args = f"{text} to {_tp['lang_name']}".split()
                translate_lyrics_command(update, context)
                return
        else:
            _pending_translate_lang.pop(user_id, None)
            _tp = None

    # ── Pending disambiguation follow-up ───────────────────────────────────
    # The bot just asked "Which one did you mean?" with tappable options.
    # If the user's next message names one of the ARTISTS (or a number),
    # that's a SELECTION — resolve it to "Artist - Song" and let normal
    # routing open the song card.  Anything else is a new request: clear
    # the stale options and fall through.  Runs before the regex router.
    _pend = _pending_disambig.get(user_id)
    if _pend and _pend.get('candidates'):
        if time.time() - _pend.get('ts', 0) > _DISAMBIG_TTL:
            _pending_disambig.pop(user_id, None)
        else:
            _choice = _match_disambiguation_choice(text,
                                                   _pend['candidates'])
            if _choice:
                _pending_disambig.pop(user_id, None)
                _pending_recommend_artist.pop(user_id, None)
                logger.info(
                    f"Disambiguation follow-up for user {user_id}: "
                    f"'{text}' → {_choice['artist']} - {_choice['song']}"
                )
                text = f"{_choice['artist']} - {_choice['song']}"
            else:
                # Not a selection — the options are stale now.
                _pending_disambig.pop(user_id, None)

    # ── Step 1: Regex router — always runs first ────────────────────────────
    # Deterministic, zero-latency, and must take priority over ALL stored
    # state.  If the user typed a new structured request, clear any pending
    # artist context immediately so it can never contaminate the new request.
    try:
        intent, query = detect_intent(text)
    except Exception:
        intent, query = None, None

    if intent:
        # Structured regex match — discard stale pending state and handle.
        _pending_recommend_artist.pop(user_id, None)
        logger.info(
            f"NL intent for user {user_id}: intent='{intent}', "
            f"query='{query}', raw='{text}'"
        )

        # ── Recommend without explicit artist → disambiguation first ─────────
        # The regex router strips keywords and returns, e.g., query='nightcall'
        # when the user typed "recommend songs like nightcall".  Executing that
        # directly picks an arbitrary artist/version of the song.  Instead:
        #   • Dominant single match → "Did you mean X — Song?" (yes / no)
        #   • Multiple matches      → list of /recommend commands
        #   • No candidates         → generic format hint
        # When the user already specified "Artist - Song" (separator present),
        # the query is unambiguous — execute normally.
        if intent == 'recommend' and query and ' - ' not in query and ' – ' not in query:
            try:
                from services.nlp_router import (
                    search_song_candidates as _sc,
                    is_dominant_match      as _is_dom,
                )
                _seed = query.strip()
                _cands = _sc(_seed)
                if _cands:
                    if _is_dom(_cands):
                        top = _cands[0]
                        _pending_confirmation[user_id] = {
                            'artist':     top['artist'],
                            'song':       top['song'],
                            'intent_cmd': 'recommend',
                        }
                        _rmsg = f"🎵 Did you mean *{top['artist']}* — *{top['song']}*?"
                    else:
                        _pending_confirmation.pop(user_id, None)
                        _lines = [
                            f"• `/recommend {c['artist']} - {c['song']}`"
                            for c in _cands[:3]
                        ]
                        _rmsg = (
                            f"🎵 Several songs match *{_seed}*.\n"
                            f"Which one did you mean?\n\n"
                            + "\n".join(_lines)
                            + f"\n\nTap one 👇 or type: `Artist - {_seed}` to be more specific."
                        )
                else:
                    _pending_confirmation.pop(user_id, None)
                    _rmsg = (
                        f"🔍 I couldn't find a song called *{md(_seed)}*.\n\n"
                        f"Please use the format: `Artist - Song`\n"
                        f"Example: `Kavinsky - Nightcall`"
                    )
                if _cands and not _is_dom(_cands):
                    _remember_disambiguation(user_id, _cands)
                    update.message.reply_text(
                        _rmsg, parse_mode='Markdown',
                        reply_markup=_disambiguation_buttons(_cands))
                else:
                    update.message.reply_text(_rmsg, parse_mode='Markdown')
            except Exception as _re:
                logger.warning(f"[regex-recommend] Disambig error: {_re}")
                # Safe fallback — execute directly
                context.args = query.split()
                recommend_command(update, context)
            return
        # ─────────────────────────────────────────────────────────────────────

        context.args = query.split() if query else []
        handler_map = {
            'lyrics': lyrics_command,
            'recommend': recommend_command,
            'artist': artist_command,
            'youtube': youtube_command,
            'trending': trending_command,
            'translate': translate_lyrics_command,
            'analyze': analyze_command,
            'stats': stats_command,
            'song': song_command,
            'top': top_command,
            'random': random_command,
            'quiz': quiz_command,
            'throwback': throwback_command,
            'subscribe': subscribe_daily_command,
            'unsubscribe': unsubscribe_daily_command,
            'wiki': wiki_command,
            'mp3': mp3_command,
            'download': download_command,
            'mood': mood_command,
        }
        handler = handler_map.get(intent)
        if handler:
            handler(update, context)
        else:
            logger.debug(f"Unknown intent '{intent}' for user {user_id}")
        return

    # ── Round 4c: duel + daily-challenge answers (A/B/C/D) ─────────────────
    # Checked before the regular quiz so the game sessions don't clash.
    # Guards (round 6 QA): an active game owns the user's next message —
    # non-answer text gets a nudge instead of silently falling through to
    # an unrelated song search while the game stays half-open.
    answer_up = text.upper()
    if user_id in active_duel_sessions:
        if len(answer_up) == 1 and answer_up in 'ABCD':
            _handle_duel_answer(update, context, user_id, answer_up)
            return
        update.message.reply_text(
            "⚔️ You're in a duel! Answer with A, B, C or D — "
            "or /cancel to forfeit. 🏳️"
        )
        return
    if user_id in active_daily:
        if len(answer_up) == 1 and answer_up in 'ABCD':
            _handle_daily_answer(update, context, user_id, answer_up)
            return
        update.message.reply_text(
            "🎯 Daily challenge in progress! Answer with A, B, C or D — "
            "or /cancel to give up. 🏳️"
        )
        return

    # ── Step 2: Quiz state ───────────────────────────────────────────────────
    quiz_data = active_quizzes.get(user_id)
    if quiz_data and quiz_data.get("state") == "active":
        answer = text.upper()
        if len(answer) == 1 and answer in 'ABCD':
            quiz_answer(update, context)
            return
        update.message.reply_text(
            "🧠 Quiz in progress! Please answer with A, B, C or D — "
            "or /cancel to stop the quiz."
        )
        return

    # ── Step 2.5: Pending dominant-match confirmation ────────────────────────
    # When the disambiguation layer showed "Did you mean X - Y?" and the match
    # was dominant (one clear winner), we store a pending confirmation.
    # "yes" / "yeah" / "sure" → execute the suggested song/intent.
    # "no" / "nope" / "cancel" → clear state and show format hint.
    # Anything else (new request) → clear state and fall through.
    if user_id in _pending_confirmation:
        tl = text.lower().strip().rstrip('!.?,')
        pend = _pending_confirmation[user_id]
        if tl in _YES_WORDS:
            _pending_confirmation.pop(user_id, None)
            _conf_cmd_map = {
                'song':      song_command,
                'lyrics':    lyrics_command,
                'recommend': recommend_command,
                'analyze':   analyze_command,
            }
            confirmed_handler = _conf_cmd_map.get(pend['intent_cmd'])
            if confirmed_handler:
                context.args = f"{pend['artist']} - {pend['song']}".split()
                update.message.chat.send_action(action="typing")
                confirmed_handler(update, context)
            return
        elif tl in _NO_WORDS:
            _no_intent = pend.get('intent_cmd', '')
            _pending_confirmation.pop(user_id, None)
            if _no_intent == 'recommend':
                update.message.reply_text(
                    "No problem! You can type the full format:\n"
                    "`Artist - Song`\n\n"
                    "For example: `Adele - Hello`",
                    parse_mode='Markdown',
                )
            else:
                update.message.reply_text(
                    "No problem! You can type the full format:\n"
                    "`Artist - Song`\n\n"
                    "For example: `Adele - Hello`",
                    parse_mode='Markdown',
                )
            return
        else:
            # User moved on to something else — clear and fall through.
            logger.info(
                f"[NLP] Clearing stale confirmation for user {user_id}: {text!r}"
            )
            _pending_confirmation.pop(user_id, None)

    # ── Step 3: Pending artist-recommend flow ────────────────────────────────
    # The user is in the middle of picking a seed song for artist-based
    # recommendations (triggered by /recommend <artist>).
    #
    # GUARD: only use the pending state when the input looks like a bare
    # song title — short (≤5 words) and free of intent-bearing keywords.
    # Any longer or keyword-carrying input means the user started a new
    # request, so we clear the pending state and fall through to NLP.
    if user_id in _pending_recommend_artist:
        words = text.strip().split()
        text_lower = text.lower()
        is_new_request = (
            len(words) > 5
            or any(kw in text_lower.split() for kw in _INTENT_KEYWORDS)
        )
        if is_new_request:
            # User moved on — clear stale state and fall through to NLP.
            logger.info(
                f"[NLP] Clearing stale pending artist for user {user_id} "
                f"(new request detected): {text!r}"
            )
            _pending_recommend_artist.pop(user_id, None)
        else:
            # Plain short text — treat as song title for pending artist.
            _pend = _pending_recommend_artist[user_id]
            if isinstance(_pend, dict):
                artist_name = _pend.get('artist', '')
                original_query = _pend.get('query', '')
            else:  # legacy plain-string state
                artist_name, original_query = _pend, ''
            from services.lyrics_service import search_song_info
            update.message.chat.send_action(action="typing")
            result = search_song_info(artist_name, text)
            valid = False
            song_query = None
            if result:
                found_artist, found_song, _ = result
                if _names_match(artist_name, found_artist):
                    # Normal case: "<song>" by the pending artist.
                    valid = True
                    song_query = f"{found_artist} - {found_song}"
                elif (original_query
                      and _names_match(text, found_artist)
                      and _query_matches_song(original_query, found_song)):
                    # Correction case: the bot guessed the wrong artist
                    # ("Which Rush song?" for the band) and the user replied
                    # with the real artist ("Ayra Starr") — the original
                    # query ("rush") was the song title all along.
                    logger.info(
                        f"[NLP] Artist correction for user {user_id}: "
                        f"'{original_query}' is '{found_artist} - {found_song}'"
                    )
                    valid = True
                    song_query = f"{found_artist} - {found_song}"
            if not valid:
                update.message.reply_text(
                    f"❌ I couldn't find \"{text}\" by {artist_name}.\n\n"
                    f"Please try another {artist_name} song title, "
                    f"or pick one from the buttons above."
                )
                return
            _pending_recommend_artist.pop(user_id, None)
            context.args = song_query.split()
            recommend_command(update, context)
            return

    # ── Step 3.5: Yes / No without a pending state ──────────────────────────
    # "yes" / "no" are only meaningful inside an active confirmation or quiz.
    # If neither state is live, treat the message as a stray reply and prompt
    # the user — do NOT pass it to the NLP layer which would interpret "Yes"
    # as a song title and trigger a Last.fm disambiguation search.
    _tl_guard = text.lower().strip().rstrip('!.?,')
    if _tl_guard in _YES_WORDS or _tl_guard in _NO_WORDS:
        update.message.reply_text(
            "🤔 Not sure what you're replying to!\n\n"
            "Try a command like:\n"
            "• /song Adele - Hello\n"
            "• /lyrics The Weeknd - Blinding Lights\n"
            "• /recommend Counting Stars"
        )
        return

    # ── Step 3.52: Greetings ────────────────────────────────────────────────
    # "hello"/"hi" are greetings, not song searches. Without this, the
    # bare-title fast path below sends them to Last.fm as song titles
    # ("Did you mean Adele — Hello?").
    _greet = text.lower().strip().rstrip('!.?,')
    if _greet in _GREETING_WORDS:
        update.message.reply_text(
            "👋 Hey there!\n\n"
            "I can find lyrics, build song dashboards, recommend music, "
            "grab MP3s and more.\n\n"
            "Try:\n"
            "• `Artist - Song` (e.g. `Tyla - Water`)\n"
            "• /random for a surprise\n"
            "• /help for everything I do"
        )
        return

    # ── Step 3.55: Bare artist name → artist card directly ──────────────────
    # Typing just an artist's name ("Tate McRae") should show their artist
    # card — not a "which song did you mean?" prompt. The local-DB lookup is
    # free (no network, no added latency). If the name is ALSO a known song
    # title, fall through to the disambiguation prompt as before.
    if _is_bare_title_fast_path(text):
        _bare_artist = get_artist_info(text.strip())
        if _bare_artist and text.strip().lower() not in _local_song_titles():
            _pending_recommend_artist.pop(user_id, None)
            _pending_disambig.pop(user_id, None)
            logger.info(
                f"NL bare artist name for user {user_id}: "
                f"'{text.strip()}' → artist card"
            )
            context.args = text.strip().split()
            artist_command(update, context)
            return

    # ── Step 3.6: Bare-title fast path ───────────────────────────────────────
    # Short keyword-less inputs ("water", "blinding lights") skip the OpenAI
    # round-trip and go straight to Last.fm disambiguation — the NLP layer
    # could never resolve these confidently anyway (see _is_bare_title_fast_path).
    if _is_bare_title_fast_path(text):
        _pending_recommend_artist.pop(user_id, None)
        # Cap the seed: a paste accident must not become a pathological
        # 500-char API query. Then fix obvious typos against known titles
        # ("calin down" → "Calm Down") before the Last.fm search.
        _seed = text.strip()[:100]
        try:
            from intent_router import _fuzzy_correct_title as _fp_fuzzy
            _seed = _fp_fuzzy(_seed)
        except Exception:
            pass
        try:
            from services.nlp_router import (
                search_song_candidates as _fp_search,
                is_dominant_match      as _fp_is_dom,
                disambiguation_message as _fp_disambig,
            )
            _fp_cands = _fp_search(_seed)
            # ── General bare-artist check ────────────────────────────────
            # Typing just an artist's name ("Justin Bieber") should show the
            # artist card — not song suggestions — even when the artist is
            # outside the 43-name local DB (Step 3.55 only covers those).
            # Conflict-free: fires only when ALL candidates are by ONE
            # artist AND the input covers that artist's name.  "Ghost"
            # (many artists) and "Blinding Lights" (input isn't the artist
            # name) fall through to song disambiguation exactly as before.
            _bare_live = None
            if _fp_cands and _seed.lower() not in _local_song_titles():
                _bare_live = _sole_artist_name(_seed, _fp_cands)
            if _bare_live:
                _pending_recommend_artist.pop(user_id, None)
                _pending_disambig.pop(user_id, None)
                _pending_confirmation.pop(user_id, None)
                logger.info(
                    f"NL bare artist name (live) for user {user_id}: "
                    f"'{_seed}' -> artist card ({_bare_live})"
                )
                context.args = _bare_live.split()
                artist_command(update, context)
                return
            if _fp_cands:
                if _fp_is_dom(_fp_cands):
                    _fp_top = _fp_cands[0]
                    _pending_confirmation[user_id] = {
                        'artist':     _fp_top['artist'],
                        'song':       _fp_top['song'],
                        'intent_cmd': 'song',
                    }
                else:
                    _pending_confirmation.pop(user_id, None)
                _fp_msg = _fp_disambig(_seed, 'song', _fp_cands)
            else:
                _pending_confirmation.pop(user_id, None)
                _fp_msg = (
                    f"🔍 I couldn't find a song called *{md(_seed)}*.\n\n"
                    "Please use the format:\n"
                    "`Artist - Song`\n\n"
                    "Example: `Tyla - Water`"
                )
            if _fp_cands and not _fp_is_dom(_fp_cands):
                # Multi-candidate list → tappable buttons + remember the
                # options so the next message can select one by artist name.
                _remember_disambiguation(user_id, _fp_cands)
                update.message.reply_text(
                    _fp_msg, parse_mode='Markdown',
                    reply_markup=_disambiguation_buttons(_fp_cands))
            else:
                update.message.reply_text(_fp_msg, parse_mode='Markdown')
        except Exception as _fp_err:
            logger.warning(f"[fast-path] Disambiguation error: {_fp_err}")
        return

    # ── Step 4: NLP fallback ─────────────────────────────────────────────────
    # Clear any remaining stale pending state before handing off to NLP,
    # so the NLP path always starts from a clean slate.
    _pending_recommend_artist.pop(user_id, None)

    # ── Step 4 (continued): NLP FALLBACK ─────────────────────────────────────
    # OpenAI Responses API (gpt-5.4-mini) — only reached when the regex
    # router returned no match.  Non-intrusive: only routes to existing
    # handlers, never generates content itself.
    #
    # TWO INDEPENDENT SAFETY LAYERS:
    #   Layer 1 — Confidence:  >= 0.7 execute / 0.4–0.7 clarify / < 0.4 low_conf
    #   Layer 2 — Entity gate: deterministic check for required entities.

    # ── Step 3.9: Non-verbal input ──────────────────────────────────────────
    # Pure emoji/punctuation would burn a paid OpenAI call on zero
    # information. Answer directly instead.
    if not re.search(r'[^\W_]', text):
        update.message.reply_text(
            "🤖 I work with words!\n\n"
            "Try `Artist - Song` (e.g. `Tyla - Water`),\n"
            "or /help to see what I can do."
        )
        return

    try:
        from services.nlp_router import (
            parse_intent           as nlp_parse,
            entity_gate            as nlp_entity_gate,
            build_query            as nlp_build_query,
            clarification_message  as nlp_clarify,
            low_confidence_message as nlp_low_conf_msg,
            search_song_candidates as nlp_search_candidates,
            disambiguation_message as nlp_disambig_msg,
        )

        nlp        = nlp_parse(text)
        nlp_intent = nlp.get("intent", "unknown")
        nlp_conf   = nlp.get("confidence", 0.0)
        nlp_artist = nlp.get("artist")
        nlp_song   = nlp.get("song")

        _nlp_handler_map = {
            'lyrics':    lyrics_command,
            'song':      song_command,
            'recommend': recommend_command,
            'analyze':   analyze_command,
        }

        # ── Layer 1: confidence tier ───────────────────────────────────────
        if nlp_intent == "unknown" or nlp_conf < 0.4:
            conf_tier = "low_conf"
        elif nlp_conf < 0.7:
            conf_tier = "clarify"
        else:
            conf_tier = "execute"

        # ── Layer 2: entity gate ───────────────────────────────────────────
        gate = nlp_entity_gate(nlp, text)

        # ── Combine layers (decision table) ───────────────────────────────
        # Rule: if the entity gate says we have enough to act (artist + song
        # present for song/lyrics/analyze, or at least one entity for recommend),
        # execute regardless of confidence.  Confidence reflects how sure the
        # model is about *intent*, but if we already have concrete entities,
        # the search itself will confirm or fail gracefully.
        if conf_tier == "execute" and gate == "execute":
            final = "execute"
        elif gate == "execute":
            final = "execute"
        elif conf_tier == "low_conf" and gate == "low_conf":
            final = "low_conf"
        elif gate == "clarify":
            final = "clarify"
        elif conf_tier == "low_conf":
            final = "low_conf"
        else:
            final = "clarify"

        logger.info(
            f"[NLP] user={user_id} intent={nlp_intent!r} "
            f"artist={nlp_artist!r} song={nlp_song!r} "
            f"conf={nlp_conf:.2f} conf_tier={conf_tier} "
            f"gate={gate} final={final}"
        )

        if final == "execute":
            # ── Recommend without explicit artist → confirm before executing ──
            # When the intent is recommendation and the user did NOT name an
            # artist, firing immediately would pick an arbitrary version of the
            # song.  Instead run a disambiguation step so the user controls
            # exactly which seed track is used.
            #
            # • Dominant single match → "Did you mean X — Song?" (yes / no)
            # • Multiple matches      → list of /recommend commands to pick from
            # • No candidates         → generic format hint
            #
            # This block applies ONLY to recommend/similar.  Lyrics, song, and
            # analyze flows are unaffected.
            if nlp_intent == "recommend" and not nlp_artist and nlp_song:
                try:
                    from services.nlp_router import is_dominant_match as _is_dom
                    _rec_cands = nlp_search_candidates(nlp_song)
                    if _rec_cands:
                        if _is_dom(_rec_cands):
                            top = _rec_cands[0]
                            _pending_confirmation[user_id] = {
                                'artist':     top['artist'],
                                'song':       top['song'],
                                'intent_cmd': 'recommend',
                            }
                            _rec_msg = (
                                f"🎵 Did you mean *{top['artist']}* — *{top['song']}*?"
                            )
                        else:
                            _pending_confirmation.pop(user_id, None)
                            top3 = _rec_cands[:3]
                            _lines = [
                                f"• `/recommend {c['artist']} - {c['song']}`"
                                for c in top3
                            ]
                            _rec_msg = (
                                f"🎵 Several songs match *{nlp_song}*.\n"
                                f"Which one did you mean?\n\n"
                                + "\n".join(_lines)
                                + f"\n\nTap one 👇 or type: `Artist - {nlp_song}` to be more specific."
                            )
                    else:
                        _pending_confirmation.pop(user_id, None)
                        _rec_msg = (
                            f"🔍 I couldn't find a song called *{md(nlp_song)}*.\n\n"
                            f"Please use the format: `Artist - Song`\n"
                            f"Example: `Kavinsky - Nightcall`"
                        )
                    if _rec_cands and not _is_dom(_rec_cands):
                        _remember_disambiguation(user_id, _rec_cands)
                        update.message.reply_text(
                            _rec_msg, parse_mode='Markdown',
                            reply_markup=_disambiguation_buttons(_rec_cands))
                    else:
                        update.message.reply_text(_rec_msg, parse_mode='Markdown')
                except Exception as _rec_err:
                    logger.warning(f"[NLP] Recommend disambig error: {_rec_err}")
                    # Something broke — fall through to direct execute as a safe fallback
                    nlp_query = nlp_build_query(nlp)
                    context.args = nlp_query.split() if nlp_query else []
                    handler = _nlp_handler_map.get(nlp_intent)
                    if handler:
                        update.message.chat.send_action(action="typing")
                        handler(update, context)
            else:
                nlp_query = nlp_build_query(nlp)
                context.args = nlp_query.split() if nlp_query else []
                handler = _nlp_handler_map.get(nlp_intent)
                if handler:
                    update.message.chat.send_action(action="typing")
                    handler(update, context)

        else:
            # ── Unified non-execute path ───────────────────────────────────
            # Disambiguation is driven by ENTITY STATE, not confidence tier.
            #
            # Rule A: Song extracted, artist missing → Last.fm candidates.
            # Rule B: ≤2 words, no entities extracted → try text as song name.
            # Rule C: No song to search → generic clarify / format prompt.

            _raw_words = text.strip().split()
            song_to_search = None

            if nlp_song and not nlp_artist:
                song_to_search = nlp_song
            elif not nlp_song and not nlp_artist and len(_raw_words) <= 2:
                # Only treat bare text as a song name if it contains at least
                # 2 alphabetic characters.  Inputs like "???" or "123" have no
                # meaningful content and would only produce junk Last.fm results.
                _candidate = text.strip()
                if sum(1 for c in _candidate if c.isalpha()) >= 2:
                    song_to_search = _candidate

            _nlp_multi_cands = None  # set when a tappable option list is shown
            if song_to_search:
                try:
                    from services.nlp_router import is_dominant_match as _is_dom
                    candidates = nlp_search_candidates(song_to_search)
                    if candidates:
                        _display_intent = (
                            nlp_intent if nlp_intent != "unknown" else "song"
                        )
                        # Store pending confirmation when there is one clear
                        # dominant match so the user can reply "yes" to confirm.
                        if _is_dom(candidates):
                            top = candidates[0]
                            _pending_confirmation[user_id] = {
                                'artist':     top['artist'],
                                'song':       top['song'],
                                'intent_cmd': _display_intent,
                            }
                        else:
                            # Multiple options shown — no single "yes" target.
                            _pending_confirmation.pop(user_id, None)
                        msg = nlp_disambig_msg(
                            song_to_search, _display_intent, candidates
                        )
                        if not _is_dom(candidates):
                            _nlp_multi_cands = candidates
                    else:
                        msg = nlp_low_conf_msg()
                except Exception as _de:
                    logger.warning(f"[NLP] Disambiguation error: {_de}")
                    msg = (
                        nlp_clarify(nlp)
                        if final == "clarify"
                        else nlp_low_conf_msg()
                    )
            elif final == "clarify":
                msg = nlp_clarify(nlp)
            else:
                msg = nlp_low_conf_msg()

            if _nlp_multi_cands:
                # Tappable option buttons + remember for follow-up selection.
                _remember_disambiguation(user_id, _nlp_multi_cands)
                update.message.reply_text(
                    msg, parse_mode='Markdown',
                    reply_markup=_disambiguation_buttons(_nlp_multi_cands))
            else:
                update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as nlp_err:
        logger.warning(f"[NLP] Fallback error for user {user_id}: {nlp_err}")


def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    # Stale/tapped-twice callbacks raise here — never let that kill the tap.
    try:
        query.answer()
    except Exception:
        pass

    data = query.data
    if ':' not in data:
        return

    action, param = data.split(':', 1)
    # Resolve token-registry payloads (long/Arabic/emoji queries) back to
    # the full query; inline payloads pass through unchanged.
    from buttons import cb_resolve
    param = cb_resolve(param)
    user_id = update.effective_user.id
    _pending_recommend_artist.pop(user_id, None)
    _pending_disambig.pop(user_id, None)
    logger.info(f"Callback from user {user_id}: action='{action}', param='{param}'")

    if action == 'noop':
        return

    if action == 'subcount':
        try:
            count = int(param)
            chat_id = update.effective_chat.id
            subscribe_user(user_id, chat_id, daily_count=count)
            query.message.reply_text(
                f"🔔 You're subscribed!\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You'll receive {count} song{'s' if count > 1 else ''} per day.\n\n"
                "Every day you'll get curated songs with:\n"
                "• Full lyrics and mood analysis\n"
                "• Word statistics and patterns\n"
                "• Fresh discoveries to explore\n\n"
                "Your first pick arrives tomorrow! 🎶\n\n"
                "To stop: /unsubscribe"
            )
        except Exception as e:
            logger.error(f"Error in subcount callback for user {user_id}: {e}")
            query.message.reply_text("😓 Something went wrong. Please try /subscribe again.")
        return

    context.args = param.split() if param else []

    handler_map = {
        'lyrics': lyrics_command,
        'recommend': recommend_command,
        'more_recs': more_recs_command,
        'artist': artist_command,
        'youtube': youtube_command,
        'mp3': mp3_command,
        'trending': trending_command,
        'translate': translate_lyrics_command,
        'translate_to': translate_to_prompt,
        'analyze': analyze_command,
        'stats': stats_command,
        'song': song_command,
        'top': top_command,
        'random': random_command,
        'wiki': wiki_command,
        'artistsongs': _artist_songs_picker_command,
        'mood': mood_command,
        'decade': throwback_command,
        'emoji_exit': emoji_exit_callback,
    }

    handler = handler_map.get(action)
    if handler:
        class FakeMessage:
            def __init__(self, real_message, chat):
                self._msg = real_message
                self.chat = chat
                self.message_id = real_message.message_id

            def reply_text(self, *args, **kwargs):
                return self._msg.reply_text(*args, **kwargs)

            def reply_video(self, *args, **kwargs):
                return self._msg.reply_video(*args, **kwargs)

            def reply_audio(self, *args, **kwargs):
                return self._msg.reply_audio(*args, **kwargs)

        fake_update = type('FakeUpdate', (), {
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat,
            'message': FakeMessage(query.message, query.message.chat),
            'effective_message': query.message,
        })()

        try:
            handler(fake_update, context)
        except Exception as e:
            logger.error(f"Error in callback handler for action '{action}': {str(e)}")
            query.message.reply_text("Something went wrong. Please try again!")


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
                "Examples:\n"
                "• /lyrics Queen - Bohemian Rhapsody\n"
                "• /lyrics Eminem - Lose Yourself\n\n"
                "Give it a try! 🎵"
            )
            return

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for user {user_id}, query: '{query}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find those lyrics.\n\n"
                "Try with the full format:\n"
                "• /lyrics Queen - Bohemian Rhapsody\n"
                "• /lyrics Eminem - Lose Yourself\n\n"
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
        btn_query = display_title if display_title else query
        if len(chunks) == 1:
            update.message.reply_text(first_message, reply_markup=lyrics_buttons(btn_query))
        else:
            update.message.reply_text(first_message)

        for i, chunk in enumerate(chunks[1:], 1):
            continuation_header = f"🎵 Continuation ({i+1}/{len(chunks)})...\n\n"
            if i == len(chunks) - 1:
                update.message.reply_text(continuation_header + chunk, reply_markup=lyrics_buttons(btn_query))
            else:
                update.message.reply_text(continuation_header + chunk)

        logger.info(f"Successfully sent lyrics to user {user_id}")
        if display_title:
            _last_song[user_id] = display_title


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
                "• /stats The Weeknd - Blinding Lights\n\n"
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
                "Try with the full format:\n"
                "• /stats Ed Sheeran - Perfect\n"
                "• /stats The Weeknd - Blinding Lights\n\n"
                "Need help? Use /help to see examples! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)
        stats = get_song_statistics(lyrics)
        formatted_stats = format_statistics(stats)

        response = (
            f"🎵 {display_title}\n\n"
            f"{formatted_stats}"
        )

        try:
            btn_query = display_title if display_title else query
            markup = stats_buttons(btn_query)
        except Exception:
            markup = None
        processing_msg.edit_text(response, reply_markup=markup)
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

        # Visible progress — recommendations can take several seconds on a
        # cold cache (Last.fm similarity + genre + tag lookups, sequential).
        update.message.reply_text(
            f"🔍 Finding songs like \"{query}\"…\n"
            "This usually takes a few seconds. 🎵"
        )
        update.message.chat.send_action(action="typing")

        # "artist:" prefix (sent by artist-dashboard buttons) forces artist
        # mode and skips the artist-vs-song disambiguation below.
        force_artist_mode = False
        if query.lower().startswith('artist:'):
            force_artist_mode = True
            query = query[len('artist:'):].strip()

        if query and (_is_artist_only_query(query) or force_artist_mode):
            clean = clean_input(query)
            info = get_artist_info(clean)
            artist_display = info['name'] if info else clean.title()

            if not force_artist_mode:
                # The query is a known artist name BUT could also be a song
                # title ("rush" = the band Rush AND songs by Ayra Starr /
                # Troye Sivan). Ask which one instead of guessing wrong.
                try:
                    from services.nlp_router import (
                        search_song_candidates as _am_search,
                    )
                    from buttons import _cb as _am_cb
                    _am_cands = _am_search(query) or []
                except Exception as _am_err:
                    logger.warning(f"[recommend] artist/song check failed: {_am_err}")
                    _am_cands = []
                if _am_cands and _am_cands[0]['artist'].lower() != artist_display.lower():
                    _am_rows = [[
                        InlineKeyboardButton(
                            f"🎤 Artist: {artist_display}",
                            callback_data=_am_cb("recommend", f"artist:{artist_display}"),
                        )
                    ]]
                    for _c in _am_cands[:3]:
                        _am_rows.append([
                            InlineKeyboardButton(
                                f"🎵 {_c['song']} — {_c['artist']}",
                                callback_data=_am_cb(
                                    "recommend", f"{_c['artist']} - {_c['song']}"
                                ),
                            )
                        ])
                    update.message.reply_text(
                        f"🤔 \"{md(query)}\" could be an artist *or* a song.\n"
                        "Which did you mean?",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(_am_rows),
                    )
                    return

            top_songs = _fetch_artist_top_songs(artist_display)
            if top_songs:
                _pending_recommend_artist[user_id] = {
                    'artist': artist_display,
                    'query': query,
                }
                update.message.reply_text(
                    f"🎧 Which {artist_display} song should I use to find similar songs?\n\n"
                    "Pick one below or type another song manually:",
                    reply_markup=recommend_pick_buttons(artist_display, top_songs)
                )
                return
            update.message.reply_text(
                f"😕 I couldn't find enough info for \"{query}\" to recommend songs.\n\n"
                "Try with a specific song:\n"
                f"• /recommend {query} - [song name]"
            )
            return

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

        btn_query = display_title if display_title else query
        markup = recommend_results_buttons(btn_query, recommendations)
        update.message.reply_text(formatted_recommendations, reply_markup=markup)
        # Remember shown artists so "🔄 More like this" serves fresh picks.
        _shown_recs[(user_id, btn_query.lower())] = [
            r['artist'].lower() for r in recommendations
        ]
        logger.info(f"Successfully sent recommendations to user {user_id}")
        # Round 4: taste stats (local only)
        try:
            log_interaction(user_id, 'recommend', genre=_safe_genre(use_artist))
        except Exception as _e:
            logger.debug(f"round4 stats hook failed: {_e}")

    except Exception as e:
        logger.error(f"Error processing recommend command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while getting recommendations.\n"
            "Please try again in a moment! 🔄"
        )


def more_recs_command(update: Update, context: CallbackContext):
    """Handle the '🔄 More like this' button — fresh recommendations."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args).strip()
        if not query:
            update.message.reply_text(
                "😕 I lost track of the original song. Try /recommend again! 🎵"
            )
            return

        update.message.reply_text(
            f"🔄 Digging deeper for songs like \"{query}\"…\n"
            "One moment! 🎵"
        )
        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)
        if not lyrics:
            update.message.reply_text(
                "😕 I couldn't re-find that song (the button link may have been cut short).\n"
                "Try /recommend with the full \"Artist - Song\" name! 🔍"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)
        mood = detect_song_mood(lyrics)
        use_artist = artist if artist else query
        use_song = song if song else query

        exclude = _shown_recs.get((user_id, query.lower()), [])
        if not exclude:
            exclude = _shown_recs.get((user_id, display_title.lower()), [])

        fresh = get_similar_songs_fresh(use_artist, use_song, mood,
                                        exclude_artists=exclude)
        if len(fresh) < 3:
            update.message.reply_text(
                f"🎵 That's everything I've got for \"{display_title}\" for now!\n"
                "Try /recommend with a different song for new ideas. ✨"
            )
            return

        shown = _shown_recs.setdefault((user_id, query.lower()), [])
        for r in fresh:
            ak = r['artist'].lower()
            if ak not in shown:
                shown.append(ak)

        formatted = format_recommendations(fresh, display_title)
        btn_query = display_title if display_title else query
        markup = recommend_results_buttons(btn_query, fresh)
        update.message.reply_text(formatted, reply_markup=markup)
        logger.info(f"Sent fresh recommendations to user {user_id} for '{display_title}'")

    except Exception as e:
        logger.error(f"Error in more_recs for user {user_id}: {e}")
        update.message.reply_text(
            "😓 Couldn't fetch more songs right now. Try again in a moment! 🔄"
        )


def _parse_translate_language(query: str):
    """Split '<song> to <language>' — also handles a bare 'to <language>'.

    The trailing word is only treated as a language when it is actually
    supported: that keeps song titles like "Ariana Grande - Into You" (or a
    bare "Into You") from being misread as a language suffix.  A trailing
    unknown word after a real song ("X to Klingon") keeps the old
    unsupported-language error path.
    """
    match = re.search(r'(?:^|\s+)(?:to|into|in)\s+(\w+)\s*$', query, re.IGNORECASE)
    if match:
        lang_name = match.group(1).strip()
        lang_code = get_language_code(lang_name)
        song_query = query[:match.start()].strip()
        if lang_code:
            return song_query, lang_code, lang_name
        if song_query and not song_query.rstrip().endswith('-'):
            # "Adele - Hello to Klingon" → unsupported-language error path.
            return song_query, None, lang_name
        # Bare "Into You", or "Artist - Into You" — a song title, not a suffix.
        return query, None, None
    return query, None, None


def _extract_language_name(text: str):
    """Find a supported language name inside free text.

    Returns (lang_code, matched_word) or (None, None).  Lets answers like
    "Spanish" — or a full sentence such as "spanish please" — resolve to
    a language when the bot asked "which language?".
    """
    code = get_language_code(text)
    if code:
        return code, text.strip()
    for word in re.findall(r'[A-Za-zÀ-ÿ]+', text or ''):
        code = get_language_code(word)
        if code:
            return code, word
    return None, None


def translate_to_prompt(update: Update, context: CallbackContext):
    """Callback for the '🌐 Translate to…' song-card button.

    Asks the user which language they want; their next message (a bare
    language name) is resolved by natural_language_handler against the
    stored song query.  The 🌍 Arabic button path is untouched.
    """
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        logger.info(f"User {user_id} tapped Translate-to for: '{query}'")
        if not query:
            update.message.reply_text(
                "😕 I lost track of which song you meant.\n"
                "Tap 🌐 Translate to… on a song card and I'll ask for the language! 🎵"
            )
            return
        _pending_translate_lang[user_id] = {
            'query': query, 'lang_code': None, 'lang_name': None,
            'ts': time.time(),
        }
        update.message.reply_text(
            "🌐 Which language should I translate the lyrics to?\n\n"
            "Just type it — e.g. *Spanish*, *French*, *Turkish*…",
            parse_mode='Markdown',
        )
    except Exception as e:
        logger.error(f"Error in translate_to prompt for user {user_id}: {e}")
        update.message.reply_text("😓 Something went wrong. Please try again!")


def translate_lyrics_command(update: Update, context: CallbackContext):
    """Handle the /translate command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        logger.info(f"User {user_id} raw translate input: '{query}'")

        if not query:
            supported = get_supported_languages_text()
            update.message.reply_text(
                "⚠️ Please tell me what song to translate!\n\n"
                "Examples:\n"
                "• /translate Adele - Hello\n"
                "• /translate Coldplay - Yellow to spanish\n"
                "• /translate Dua Lipa - One Kiss to french\n\n"
                f"Supported languages: {supported}\n\n"
                "Let's try again! 🎵"
            )
            return

        song_query, lang_code, lang_name = _parse_translate_language(query)

        if lang_name and not lang_code:
            supported = get_supported_languages_text()
            update.message.reply_text(
                f"😕 Sorry, I don't support \"{lang_name}\" as a language.\n\n"
                f"Supported languages: {supported}\n\n"
                "Examples:\n"
                "• /translate Dua Lipa - One Kiss to French\n"
                "• /translate Coldplay - Yellow to spanish"
            )
            return

        if not song_query and lang_code:
            # "Translate to Spanish" with no song named — apply it to the
            # song the user is currently viewing; otherwise ask which song.
            song_query = _last_song.get(user_id)
            if song_query:
                logger.info(
                    f"User {user_id} translate-to-{lang_code} with no song: "
                    f"using last viewed song '{song_query}'"
                )
            else:
                _pending_translate_lang[user_id] = {
                    'query': None, 'lang_code': lang_code,
                    'lang_name': lang_name, 'ts': time.time(),
                }
                update.message.reply_text(
                    f"🌐 Which song should I translate to *{lang_name}*?\n\n"
                    "Type `Artist - Song` — e.g. `Adele - Hello`.",
                    parse_mode='Markdown',
                )
                return

        if not lang_code:
            lang_code = 'ar'

        lang_display = get_language_display(lang_code)

        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(song_query)

        if not lyrics:
            logger.info(f"No lyrics found for translation, query: '{song_query}'")
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
            f"🔄 Translating to {lang_display}... Please wait! ✨"
        )

        translated_lyrics = translate_text(lyrics, lang_code)
        if translated_lyrics:
            formatted_lyrics = format_lyrics(translated_lyrics)
            header = (
                f"🎵 {display_title}\n"
                f"🌍 {lang_display} Translation:\n\n"
            )
            # Chunk like /lyrics does — a single edit_text of a long song
            # exceeds Telegram's 4096-char limit and the user gets an error
            # after waiting through the whole translation.
            max_chunk_size = 3000
            chunks = [formatted_lyrics[i:i + max_chunk_size]
                      for i in range(0, len(formatted_lyrics), max_chunk_size)]
            processing_msg.edit_text(header + chunks[0])
            for i, chunk in enumerate(chunks[1:], 1):
                update.message.reply_text(
                    f"🌍 Continuation ({i+1}/{len(chunks)})...\n\n" + chunk
                )
            logger.info(f"Successfully sent {lang_display} translated lyrics to user {user_id}")
        else:
            logger.warning(f"Translation failed for user {user_id}")
            processing_msg.edit_text(
                "😓 I found the lyrics but the translation service is unavailable right now.\n"
                "Please try again in a few moments! 🧞‍♂️\n\n"
                f"In the meantime, try /lyrics {song_query} to see the original lyrics!"
            )

    except Exception as e:
        logger.error(f"Error processing translate command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "🤖 Oops! Something went wrong with the translation.\n"
            "Let's try that again in a moment! 🔄"
        )


def send_daily_song(context: CallbackContext):
    """Send daily song(s) to all subscribed users."""
    try:
        logger.info("Starting daily song distribution")

        subscribed = get_subscribed_users()
        logger.info(f"Sending daily songs to {len(subscribed)} users")

        for user_id, data in subscribed.items():
            try:
                daily_count = data.get("daily_count", 1)

                collected = []
                seen_keys = set()
                attempts = 0
                while len(collected) < daily_count and attempts < daily_count * 3:
                    attempts += 1
                    song, lyrics, analysis = get_daily_song()
                    if not all([song, lyrics, analysis]):
                        continue
                    song_key = f"{song['artist']} - {song['song']}"
                    if song_key in seen_keys:
                        continue
                    seen_keys.add(song_key)
                    collected.append((song, lyrics, analysis))

                if not collected:
                    logger.error(f"No daily songs available for user {user_id}")
                    continue

                if daily_count == 1:
                    song, lyrics, analysis = collected[0]
                    song_key = f"{song['artist']} - {song['song']}"
                    message = format_daily_song(song, lyrics, analysis)
                    markup = daily_song_buttons(song_key)
                    context.bot.send_message(
                        chat_id=data["chat_id"],
                        text=message,
                        reply_markup=markup
                    )
                else:
                    songs_for_picker = [{"artist": s["artist"], "song": s["song"]} for s, _, __ in collected]
                    lines = [f"🎵 Daily Discovery — {daily_count} Songs\n━━━━━━━━━━━━━━━━━━━━━\n"]
                    for i, (s, _, __) in enumerate(collected, 1):
                        lines.append(f"{i}. {s['artist']} — {s['song']}")
                    lines.append("\n\nTap a song below to open the full dashboard:")
                    message = "\n".join(lines)
                    markup = daily_picker_buttons(songs_for_picker)
                    context.bot.send_message(
                        chat_id=data["chat_id"],
                        text=message,
                        reply_markup=markup
                    )

                logger.info(f"Sent {len(collected)} daily song(s) to user {user_id}")
            except Unauthorized:
                # User blocked the bot or deleted their account — stop
                # retrying them every day (round 6 QA).
                logger.warning(
                    f"User {user_id} blocked the bot; auto-unsubscribing")
                try:
                    unsubscribe_user(user_id)
                except Exception:
                    pass
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

        raw = get_subscriber_data(user_id)
        if raw and raw.get("active"):
            count = raw.get("daily_count", 1)
            update.message.reply_text(
                "🎵 You're already subscribed!\n\n"
                f"Your daily song {'discoveries are' if count > 1 else 'discovery is'} active "
                f"({count} song{'s' if count > 1 else ''} per day).\n\n"
                "To stop: /unsubscribe"
            )
            return

        update.message.reply_text(
            "🔔 How many songs would you like per day?\n\n"
            "Choose below:",
            reply_markup=subscribe_count_buttons()
        )
        logger.info(f"Shown subscribe count options to user {user_id}")

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
                "👋 You're unsubscribed.\n\n"
                "Daily song discovery has been stopped.\n\n"
                "You can rejoin anytime with:\n"
                "/subscribe 🎵"
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
                "• /youtube The Weeknd - Starboy\n"
                "• /youtube Drake - God's Plan\n\n"
                "Let's try again! 🎵"
            )
            return

        if _is_artist_only_query(query):
            from urllib.parse import quote
            clean = clean_input(query)
            info = get_artist_info(clean)
            artist_display = info['name'] if info else clean.title()
            slug = quote(artist_display)
            top_url = f"https://www.youtube.com/results?search_query={slug}+top+videos"
            official_url = f"https://www.youtube.com/results?search_query={slug}+official+music+videos"
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Top Videos", url=top_url)],
                [InlineKeyboardButton("🎵 Official Music Videos", url=official_url)],
            ])
            update.message.reply_text(
                f"🎬 YouTube — {artist_display}\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "What would you like to watch?",
                reply_markup=markup
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
        display_song = used_song if used_song else ''
        response = format_youtube_response(display_artist, display_song, url)
        update.message.reply_text(response)
        logger.info(f"Successfully sent YouTube link to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing youtube command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while getting the YouTube link.\n"
            "Please try again in a moment! 🔄"
        )


# Artist top songs, taken from the artist's own page (Apple's artist ranking =
# the "Top Songs" order on the Apple Music artist page, i.e. what's popular for
# THIS artist right now), then Last.fm top tracks, then the static local DB as
# a last resort.  Results are cached 12h per artist so cards stay fast.
# Never raises; [] when every source misses.
_top_songs_cache = {}
_TOP_SONGS_TTL = 12 * 3600


def _itunes_artist_top_songs(artist_name: str, limit: int = 5) -> list:
    """Apple's popularity-ranked songs for this artist (the artist page order).

    Returns [song, ...] in Apple's ranking.  [] when unreachable / no match.
    """
    resp = requests.get(
        'https://itunes.apple.com/search',
        params={'term': artist_name, 'media': 'music', 'entity': 'song',
                'attribute': 'artistTerm', 'limit': 50},
        timeout=5
    )
    if resp.status_code != 200:
        logger.warning(f"iTunes artist songs failed for '{artist_name}': status={resp.status_code}")
        return []
    results = resp.json().get('results', [])
    seen = set()
    songs = []
    artist_lower = artist_name.strip().lower()
    artist_words = set(artist_lower.split())
    for r in results:
        aname = (r.get('artistName') or '').lower()
        tname = (r.get('trackName') or '').strip()
        if not tname or tname in seen:
            continue
        aname_words = set(aname.replace(',', ' ').replace('&', ' ').split())
        if artist_lower in aname or artist_words <= aname_words:
            seen.add(tname)
            songs.append(tname)
            if len(songs) >= limit:
                break
    if songs:
        logger.info(f"iTunes artist page returned {len(songs)} songs for '{artist_name}'")
    return songs


def _lastfm_artist_top_songs(artist_name: str, limit: int = 5) -> list:
    """Last.fm artist.getTopTracks (all-time most-played).  [] on any miss."""
    api_key = os.environ.get('LASTFM_API_KEY', '')
    if not api_key:
        logger.warning("LASTFM_API_KEY not available for top tracks lookup")
        return []
    resp = requests.get(
        'https://ws.audioscrobbler.com/2.0/',
        params={'method': 'artist.getTopTracks', 'artist': artist_name,
                'api_key': api_key, 'format': 'json', 'limit': 10},
        timeout=5
    )
    if resp.status_code != 200:
        logger.warning(f"Last.fm top tracks failed for '{artist_name}': status={resp.status_code}")
        return []
    tracks = resp.json().get('toptracks', {}).get('track', [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    names = [t.get('name', '').strip() for t in tracks if t.get('name', '').strip()]
    songs = list(dict.fromkeys(names))[:limit]
    if songs:
        logger.info(f"Last.fm returned {len(songs)} top tracks for '{artist_name}'")
    return songs


def _fetch_artist_top_songs(artist_name: str) -> list:
    key = (artist_name or '').strip().lower()
    if not key:
        return []
    try:
        now = time.time()
        hit = _top_songs_cache.get(key)
        if hit and (now - hit[0]) < _TOP_SONGS_TTL and hit[1]:
            return hit[1]

        songs: list = []
        try:
            songs = _itunes_artist_top_songs(artist_name)
        except Exception as e:
            logger.warning(f"iTunes artist songs error for '{artist_name}': {e}")
        if not songs:
            try:
                songs = _lastfm_artist_top_songs(artist_name)
            except Exception as e:
                logger.warning(f"Last.fm top tracks error for '{artist_name}': {e}")
        if not songs:
            # Last resort: the static local list (may be dated).
            info = get_artist_info(artist_name)
            if info:
                songs = info['top_songs'][:5]
                logger.info(f"Using static top songs for '{artist_name}' (live sources missed)")

        if songs:
            _top_songs_cache[key] = (now, songs)
        return songs
    except Exception as e:
        logger.warning(f"_fetch_artist_top_songs failed for '{artist_name}': {e}")
        return []


def _artist_songs_picker_command(update: Update, context: CallbackContext):
    artist_name = " ".join(context.args) if context.args else ""
    if not artist_name:
        update.message.reply_text("Please specify an artist name.")
        return

    top_songs = _fetch_artist_top_songs(artist_name)
    if top_songs:
        markup = artist_summary_buttons(artist_name, top_songs)
        update.message.reply_text(
            f"🎤 {artist_name}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔥 Pick a song below to explore:",
            reply_markup=markup
        )
    else:
        update.message.reply_text(
            f"😕 I couldn't find top songs for \"{artist_name}\".\n\n"
            f"Try /song {artist_name} - [song name] if you know a specific song!"
        )


def _clean_primary_artist(artist: str) -> str:
    if not artist:
        return artist
    cleaned = re.split(r'\s+(?:feat\.?|ft\.?|featuring|&|,|x\s)\s*', artist, flags=re.IGNORECASE)[0].strip()
    return cleaned if cleaned else artist


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
                "• /analyze Michael Jackson - Billie Jean\n"
                "• /analyze Adele - Rolling in the Deep\n\n"
                "I'll give you a detailed analysis! 📊"
            )
            return

        if _is_artist_only_query(query):
            clean = clean_input(query)
            info = get_artist_info(clean)
            display_name = info['name'] if info else clean.title()
            update.message.reply_text(
                f"What would you like for \"{display_name}\"?",
                reply_markup=artist_analyze_buttons(display_name)
            )
            return

        # Visible progress — analysis runs a lyric search + local stats pass.
        update.message.reply_text(
            f"🧠 Analyzing \"{query}\"…\n"
            "This usually takes a few seconds. 📊"
        )
        update.message.chat.send_action(action="typing")

        artist, song, lyrics, status = search_lyrics_with_fallback(query)

        if not lyrics:
            logger.info(f"No lyrics found for analysis, query: '{query}'")
            update.message.reply_text(
                "😕 Sorry, I couldn't find that song.\n\n"
                "Try with the full format:\n"
                "• /analyze Michael Jackson - Billie Jean\n"
                "• /analyze Adele - Rolling in the Deep\n\n"
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

        try:
            btn_query = display_title if display_title else query
            primary_artist = _clean_primary_artist(artist) if artist else None
            markup = analyze_buttons(btn_query, artist_name=primary_artist)
        except Exception:
            markup = None
        update.message.reply_text(response, reply_markup=markup)
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
            f"📚 *{md(person_info['title'])}*\n"
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

# Per-user MP3 jobs in flight — keyed (user_id, artist, song). A second tap
# while a download is running gets a "hang tight" reply instead of spawning
# a duplicate pipeline (double downloads, double rate-limit load, two files).
_mp3_in_progress = set()


def mp3_command(update: Update, context: CallbackContext):
    """Handle the MP3 button — convert a known song to MP3.

    Non-blocking: acknowledges immediately and runs the download in a
    background thread, so the bot keeps accepting inputs and answering
    while the MP3 is being prepared. The finished MP3 arrives as a new
    message when it's ready.
    """
    user_id = update.effective_user.id
    try:
        if not context.args:
            update.message.reply_text(
                "🎧 Use the MP3 button on any song result to get the audio file."
            )
            return

        raw = " ".join(context.args)
        logger.info(f"User {user_id} requested MP3: '{raw}'")

        if ' - ' in raw:
            parts = raw.split(' - ', 1)
            artist_q, song_q = parts[0].strip(), parts[1].strip()
        else:
            artist_q, song_q = raw.strip(), ''

        # Concurrency guard: one pipeline per (user, song) at a time.
        job_key = (user_id, artist_q.lower(), song_q.lower())
        if job_key in _mp3_in_progress:
            update.message.reply_text(
                "🎧 Already working on this one — hang tight!\n"
                "Your MP3 is on its way."
            )
            return
        _mp3_in_progress.add(job_key)

        chat_id = update.effective_chat.id
        update.message.reply_text(
            "🎧 On it!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Finding the audio for {raw} and converting…\n\n"
            "I'll send the MP3 here when it's ready — "
            "feel free to keep using the bot meanwhile. 🎵"
        )

        worker = threading.Thread(
            target=_mp3_background_job,
            args=(context.bot, chat_id, user_id,
                  artist_q, song_q, raw, job_key),
            daemon=True,
            name=f"mp3-{user_id}",
        )
        worker.start()

    except Exception as e:
        logger.error(f"Error in mp3 command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the MP3 conversion.\n"
            "Please try again later! 🔄"
        )


def _mp3_background_job(bot, chat_id, user_id,
                        artist_q, song_q, raw, job_key):
    """Download and deliver one MP3 in a background thread.

    Never blocks the bot's update handling: the user gets an
    acknowledgement up front (sent by mp3_command) and the finished
    audio — or a failure notice — arrives as a new message.
    """
    try:
        success, result = download_audio_for_song(artist_q, song_q)

        if not success:
            # result is the user-facing failure text (incl. YouTube search link).
            bot.send_message(chat_id=chat_id, text=result)
            return

        if result[0] == 'file_id':
            # Tier-0 hit: Telegram already hosts this file — send instantly.
            _, fid, title, uploader = result
            try:
                bot.send_audio(
                    chat_id=chat_id,
                    audio=fid,
                    caption=f"🎵 {title}\n⚡ Instant delivery",
                    title=title,
                    performer=uploader,
                )
            except Exception as send_err:
                # Stale file_id (expired/invalid): drop it and transparently
                # re-run the fresh download path instead of dead-ending.
                logger.warning(f"Stale cached file_id for '{raw}': {send_err}")
                forget_mp3_file_id(artist_q, song_q)
                bot.send_message(
                    chat_id=chat_id,
                    text="⚡ Cached copy expired — fetching a fresh one…\n"
                         "I'll send it here when it's ready. 🎵",
                )
                success2, result2 = download_audio_for_song(artist_q, song_q)
                if success2 and result2[0] != 'file_id':
                    _deliver_fresh_mp3(bot, chat_id, artist_q, song_q, result2)
                else:
                    bot.send_message(
                        chat_id=chat_id,
                        text="❌ Couldn't send the audio file.\n"
                             "Please try again in a moment. 🔄",
                    )
            return

        _deliver_fresh_mp3(bot, chat_id, artist_q, song_q, result)

    except Exception as e:
        logger.error(f"Background MP3 job failed for user {user_id} '{raw}': {e}")
        try:
            bot.send_message(
                chat_id=chat_id,
                text="😓 Something went wrong with the MP3 conversion.\n"
                     "Please try again later! 🔄",
            )
        except Exception:
            pass
    finally:
        _mp3_in_progress.discard(job_key)


def _deliver_fresh_mp3(bot, chat_id, artist_q, song_q, result):
    """Send a freshly downloaded MP3 file and remember its Telegram file_id."""
    file_path, _info_message, title, uploader = result
    try:
        with open(file_path, 'rb') as audio_file:
            sent_msg = bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                caption=f"🎵 {title}",
                title=title,
                performer=uploader,
            )
        # Remember Telegram's file_id so the next request is instant.
        try:
            if sent_msg and sent_msg.audio:
                note_mp3_file_id(artist_q, song_q, sent_msg.audio.file_id)
        except Exception:
            pass
    except Exception as send_err:
        logger.error(f"Failed to send audio: {send_err}")
        bot.send_message(
            chat_id=chat_id,
            text="❌ The MP3 was created but couldn't be sent.\n"
                 "It may be too large for Telegram (50MB limit).",
        )
    # Never delete files that live in the MP3 cache — they're reused.
    if not is_cached_mp3_path(file_path):
        cleanup_video(file_path)


def _build_fallback_artist_profile(query: str):
    try:
        import requests
        resp = requests.get(
            'https://en.wikipedia.org/api/rest_v1/page/summary/' + query.replace(' ', '_'),
            timeout=5, headers={'User-Agent': 'LyricsMasterBot/1.0'}
        )
        if resp.status_code != 200:
            resp = requests.get(
                'https://en.wikipedia.org/api/rest_v1/page/summary/' + query.title().replace(' ', '_'),
                timeout=5, headers={'User-Agent': 'LyricsMasterBot/1.0'}
            )
        if resp.status_code != 200:
            return None

        data = resp.json()
        desc = (data.get('description') or '').lower()
        extract = (data.get('extract') or '')
        music_words = ['singer', 'rapper', 'musician', 'songwriter', 'artist', 'band', 'group', 'vocalist', 'producer', 'dj', 'mc']
        if not any(w in desc for w in music_words) and not any(w in extract[:300].lower() for w in music_words):
            return None

        display_name = data.get('title', query.title())
        description = data.get('description', '')

        genre = None
        country = None
        debut = None

        genre_patterns = [
            ('pop', 'Pop'), ('rock', 'Rock'), ('hip hop', 'Hip-Hop'), ('hip-hop', 'Hip-Hop'),
            ('rap', 'Rap'), ('r&b', 'R&B'), ('rnb', 'R&B'), ('soul', 'Soul'),
            ('country', 'Country'), ('jazz', 'Jazz'), ('electronic', 'Electronic'),
            ('latin', 'Latin'), ('reggaeton', 'Reggaeton'), ('folk', 'Folk'),
            ('alternative', 'Alternative'), ('indie', 'Indie'), ('metal', 'Metal'),
            ('punk', 'Punk'), ('blues', 'Blues'), ('funk', 'Funk'), ('dance', 'Dance'),
            ('afrobeat', 'Afrobeats'), ('afrobeats', 'Afrobeats'), ('reggae', 'Reggae'), ('k-pop', 'K-Pop'),
            ('kpop', 'K-Pop'), ('amapiano', 'Amapiano'),
        ]
        extract_lower = extract[:500].lower()
        extract_orig = extract[:500]  # original case, for proper-noun filtering
        # Word-boundary matching: "dancer" must not match "dance",
        # "rapper" must not match "rap", "popular" must not match "pop".
        # Also skip matches inside multi-word capitalized phrases (proper
        # nouns like the TV show "So You Think You Can Dance").
        def _genre_present(pattern: str) -> bool:
            rx = re.compile(r'\b' + re.escape(pattern) + r'\b', re.IGNORECASE)
            for m in rx.finditer(extract_orig):
                word = extract_orig[m.start():m.end()]
                prev = re.findall(r'[A-Za-z]+', extract_orig[:m.start()][-40:])
                nxt = re.findall(r'[A-Za-z]+', extract_orig[m.end():][:40])
                # Skip proper-noun phrases: a capitalized genre word glued to
                # other capitalized words ("So You Think You Can Dance",
                # "Latin Grammy Award") is a title/award, not a genre mention.
                if word[:1].isupper() and (
                    any(w[:1].isupper() for w in prev[-2:])
                    or any(w[:1].isupper() for w in nxt[:2])
                ):
                    continue
                return True
            return bool(rx.search(desc))
        found_genres = []
        for pattern, label in genre_patterns:
            if _genre_present(pattern):
                if label not in found_genres:
                    found_genres.append(label)
        if found_genres:
            genre = ' / '.join(found_genres[:2])
        else:
            # Last-resort: a "singer"/"rapper" with no explicit genre is
            # most likely pop / hip-hop — better than a wrong guess or nothing.
            if re.search(r'\brapper\b', desc) or re.search(r'\brapper\b', extract_lower):
                genre = 'Hip-Hop'
            elif re.search(r'\bsinger\b', desc) or re.search(r'\bsinger\b', extract_lower):
                genre = 'Pop'

        country_patterns = [
            ('american', 'USA'), ('british', 'UK'), ('canadian', 'Canada'),
            ('australian', 'Australia'), ('nigerian', 'Nigeria'), ('jamaican', 'Jamaica'),
            ('south african', 'South Africa'), ('colombian', 'Colombia'),
            ('puerto rican', 'Puerto Rico'), ('barbadian', 'Barbados'),
            ('korean', 'South Korea'), ('french', 'France'), ('german', 'Germany'),
            ('irish', 'Ireland'), ('spanish', 'Spain'), ('brazilian', 'Brazil'),
            ('mexican', 'Mexico'), ('trinidadian', 'Trinidad'),
            ('english', 'UK'), ('scottish', 'UK'), ('welsh', 'UK'),
        ]
        # Take the nationality word that appears FIRST in the bio ("is a
        # Canadian singer..."), not the first pattern in our list — the old
        # code saw "American reality TV series" and wrongly picked USA.
        bio_text = f"{desc} {extract_lower}"
        best_pos = None
        for pattern, label in country_patterns:
            m = re.search(r'\b' + re.escape(pattern) + r'\b', bio_text)
            if m and (best_pos is None or m.start() < best_pos):
                best_pos = m.start()
                country = label

        debut_match = re.search(r'(?:debut|career|started|began).{0,30}?(\d{4})', extract_lower[:500])
        if debut_match:
            debut = debut_match.group(1)

        name_slug = display_name.replace(' ', '+')
        wiki_url = f"https://en.wikipedia.org/wiki/{display_name.replace(' ', '_')}"
        yt_url = f"https://www.youtube.com/results?search_query={name_slug}+official"

        lines = [f"🎤 {display_name}", "━━━━━━━━━━━━━━━━━━━━━\n"]
        if genre:
            lines.append(f"🎵 Genre: {genre}")
        if debut:
            lines.append(f"📅 Debut: {debut}")
        if country:
            lines.append(f"🌍 From: {country}")
        lines.append(f"\n🔗 Links:")
        lines.append(f"  📚 {wiki_url}")
        lines.append(f"  🎬 {yt_url}")
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔥 Pick a song below to explore:")

        top_songs = _fetch_artist_top_songs(display_name)

        return {
            'name': display_name,
            'text': '\n'.join(lines),
            'top_songs': top_songs,
        }
    except Exception as e:
        logger.warning(f"Fallback artist profile error for '{query}': {e}")
        return None


def artist_command(update: Update, context: CallbackContext):
    """Handle the /artist command."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        if not query:
            update.message.reply_text(
                "🎤 Artist Quick Info\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Usage: /artist [name]\n\n"
                "Examples:\n"
                "• /artist Taylor Swift\n"
                "• /artist Drake\n"
                "• /artist Adele"
            )
            return

        logger.info(f"User {user_id} requested artist info: '{query}'")

        info = get_artist_info(query)
        if info:
            _live_songs = _fetch_artist_top_songs(info['name']) or info.get('top_songs', [])
            update.message.reply_text(format_artist_info(info), reply_markup=artist_buttons(
                info['name'], _live_songs))
        else:
            profile = _build_fallback_artist_profile(query)
            if profile:
                top_songs = profile.get('top_songs', [])
                markup = artist_buttons(profile['name'], top_songs) if top_songs else None
                update.message.reply_text(profile['text'], disable_web_page_preview=True, reply_markup=markup)
            else:
                update.message.reply_text(
                    f"😕 I couldn't find info for \"{query}\".\n\n"
                    f"Try /wiki {query} for a broader search!"
                )

    except Exception as e:
        logger.error(f"Error in artist command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


def trending_command(update: Update, context: CallbackContext):
    """Handle the /trending command."""
    user_id = update.effective_user.id
    try:
        logger.info(f"User {user_id} requested trending songs")
        update.message.chat.send_action(action="typing")
        songs, is_live = get_trending_songs()
        try:
            markup = song_list_buttons(songs) if songs else None
        except Exception:
            markup = None
        update.message.reply_text(format_trending(songs, is_live), reply_markup=markup)

    except Exception as e:
        logger.error(f"Error in trending command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Couldn't fetch trending songs right now.\n"
            "Please try again! 🔄"
        )


@lru_cache(maxsize=200)
def _is_artist_only_query(query: str) -> bool:
    clean = clean_input(query)
    if '-' in clean:
        return False
    info = get_artist_info(clean)
    if info:
        query_words = clean.lower().split()
        name_words = info['name'].lower().split()
        if set(query_words) == set(name_words):
            return True
        if set(query_words) < set(name_words):
            return True

    # 3+ word queries are never artist-only names not already in our local DB
    # (e.g. "love story taylor swift", "blinding lights the weeknd") — skip Last.fm
    # to avoid a 200-2000ms HTTP round-trip that always returns False.
    if len(clean.split()) >= 3:
        return False

    try:
        api_key = os.environ.get('LASTFM_API_KEY')
        if api_key:
            resp = requests.get(
                'https://ws.audioscrobbler.com/2.0/',
                params={'method': 'artist.getInfo', 'artist': clean,
                        'api_key': api_key, 'format': 'json'},
                timeout=1
            )
            if resp.status_code == 200:
                data = resp.json()
                artist_data = data.get('artist', {})
                bio_content = artist_data.get('bio', {}).get('content', '')
                try:
                    listeners = int(artist_data.get('stats', {}).get('listeners', 0) or 0)
                except (ValueError, TypeError):
                    listeners = 0
                if listeners > 5000 and len(bio_content) > 50:
                    return True
    except Exception:
        pass
    return False


def _artist_summary_for_song(query: str, update, processing_msg):
    info = get_artist_info(query)
    if not info:
        processing_msg.edit_text(
            f"😕 I'm not sure if \"{query}\" is a song or an artist.\n\n"
            "Try being more specific:\n"
            f"• /song {query} [song name]\n"
            f"• /artist {query}\n\n"
            "Example: /song Tyla Water"
        )
        return

    response = (
        f"🎤 {info['name']}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎵 Genre: {info['genre']}\n"
        f"🌍 From: {info['country']}\n\n"
        "🔥 Pick a song below to explore:"
    )
    _live_top = _fetch_artist_top_songs(info['name']) or info['top_songs'][:5]
    markup = artist_summary_buttons(info['name'], _live_top)
    processing_msg.edit_text(response, disable_web_page_preview=True, reply_markup=markup)


def song_command(update: Update, context: CallbackContext):
    """Handle the /song command — full song dashboard."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        logger.info(f"User {user_id} raw song dashboard input: '{query}'")

        if not query:
            update.message.reply_text(
                "🎵 Song Dashboard\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Get a full overview of any song!\n\n"
                "Usage: /song Artist - Song\n\n"
                "Examples:\n"
                "• /song OneRepublic - Counting Stars\n"
                "• /song Ed Sheeran - Shape of You\n"
                "• /song Adele - Hello"
            )
            return

        update.message.chat.send_action(action="typing")

        processing_msg = update.message.reply_text(
            "🎵 Building your song dashboard...\n"
            "Just a moment! ✨"
        )

        _t0 = time.time()

        _ta0 = time.time()
        if _is_artist_only_query(query):
            logger.info("[song_timing] artist_check=%.0fms (redirected to artist summary)",
                        (time.time() - _ta0) * 1000)
            _artist_summary_for_song(query, update, processing_msg)
            return
        _ta1 = time.time()

        artist, song, lyrics, status = search_lyrics_with_fallback(query)
        _tl1 = time.time()

        if not lyrics:
            logger.info("[song_timing] artist_check=%.0fms  lyrics_fetch=%.0fms [%s] -> not found",
                        (_ta1 - _ta0) * 1000, (_tl1 - _ta1) * 1000, status)
            processing_msg.edit_text(
                "😕 Couldn't find that song.\n\n"
                "Try:\n"
                "• /song Water Tyla\n"
                "• /song Tyla - Water\n"
                "• /song Water"
            )
            return

        display_title = f"{artist} - {song}" if artist and song else (artist or song)

        _tan0 = time.time()
        mood = detect_song_mood(lyrics)
        stats = get_song_statistics(lyrics)
        _tan1 = time.time()

        mood_emoji = {
            'happy': '😊', 'sad': '😢', 'romantic': '💖',
            'energetic': '⚡', 'relaxed': '😌'
        }.get(mood, '🎵')

        lyrics_lines = [l.strip() for l in lyrics.strip().split('\n') if l.strip()]
        preview_lines = lyrics_lines[:4]
        lyrics_preview = '\n'.join(f"  {l}" for l in preview_lines)
        if len(lyrics_lines) > 4:
            lyrics_preview += "\n  ..."

        use_artist = artist if artist else query
        use_song = song if song else query

        # Run YouTube + recommendations in parallel — both are independent HTTP calls
        _tpar0 = time.time()
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _yt_fut  = _pool.submit(get_youtube_link, use_artist, use_song)
            _rec_fut = _pool.submit(get_similar_songs, use_artist, use_song, mood)
            yt_url = _yt_fut.result()
            recs   = _rec_fut.result()
        _tpar1 = time.time()

        logger.info(
            "[song_timing] q=%r  artist_check=%.0fms  lyrics[%s]=%.0fms  analysis=%.0fms  "
            "parallel(yt+recs)=%.0fms  TOTAL=%.0fms",
            query,
            (_ta1 - _ta0) * 1000,
            status, (_tl1 - _ta1) * 1000,
            (_tan1 - _tan0) * 1000,
            (_tpar1 - _tpar0) * 1000,
            (time.time() - _t0) * 1000,
        )

        yt_section = f"🎬 {yt_url}" if yt_url else "🎬 YouTube: not found"

        recs_lines = []
        for i, r in enumerate(recs[:3]):
            emoji = ['🔥', '✨', '💫'][i]
            recs_lines.append(f"  {emoji} {r['artist']} — {r['name']}")
        recs_text = '\n'.join(recs_lines) if recs_lines else "  No recommendations available"

        vocab_pct = stats.get('vocabulary_richness', 0)
        if vocab_pct >= 70:
            vocab_label = "Rich"
        elif vocab_pct >= 50:
            vocab_label = "Moderate"
        else:
            vocab_label = "Repetitive"

        themes = detect_themes(lyrics)
        themes_text = ', '.join(t.title() for t in themes[:3]) if themes else 'General'

        response = (
            f"🎵 {display_title}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{yt_section}\n\n"
            f"📝 Lyrics Preview:\n{lyrics_preview}\n\n"
            f"📊 Quick Stats:\n"
            f"  {mood_emoji} Mood: {mood.title()}\n"
            f"  📝 Words: {stats['total_words']} | Lines: {stats['total_lines']}\n"
            f"  🧠 Vocabulary: {vocab_pct}% ({vocab_label})\n"
            f"  🎭 Themes: {themes_text}\n\n"
            f"🎵 Similar Songs:\n{recs_text}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎤 /lyrics {query} — full lyrics\n"
            f"🔍 /analyze {query} — deep analysis"
        )

        btn_query = display_title if display_title else query
        processing_msg.edit_text(response, disable_web_page_preview=True, reply_markup=song_dashboard_buttons(btn_query))
        _last_song[user_id] = btn_query
        logger.info(f"Successfully sent song dashboard to user {user_id}")

    except Exception as e:
        logger.error(f"Error in song command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong building the dashboard.\n"
            "Please try again! 🔄"
        )


def top_command(update: Update, context: CallbackContext):
    """Handle the /top command — top songs by genre."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args)
        logger.info(f"User {user_id} requested top songs for genre: '{query}'")

        if not query:
            genres = get_available_genres()
            genre_list = ' • '.join(g.upper() if g in ('rnb', 'kpop') else g.title() for g in genres)
            update.message.reply_text(
                "🔝 Top Songs by Genre\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Usage: /top [genre]\n\n"
                f"Available: {genre_list}\n\n"
                "Examples:\n"
                "• /top afrobeats\n"
                "• /top pop\n"
                "• /top rap\n"
                "• /top rock\n"
                "• /top kpop"
            )
            return

        result = get_top_by_genre(query)
        if result:
            genre, songs = result
            try:
                markup = song_list_buttons(songs) if songs else None
            except Exception:
                markup = None
            update.message.reply_text(format_top_songs(genre, songs), reply_markup=markup)
        else:
            genres = get_available_genres()
            genre_list = ', '.join(g.upper() if g in ('rnb', 'kpop') else g.title() for g in genres)
            update.message.reply_text(
                f"😕 Genre \"{query}\" not found.\n\n"
                f"Try one of these: {genre_list}\n\n"
                "Example: /top afrobeats"
            )

        logger.info(f"Successfully sent top songs to user {user_id}")

    except Exception as e:
        logger.error(f"Error in top command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Couldn't fetch top songs right now.\n"
            "Please try again! 🔄"
        )


def random_command(update: Update, context: CallbackContext):
    """Handle the /random command — random song discovery."""
    user_id = update.effective_user.id
    try:
        logger.info(f"User {user_id} requested random song")

        update.message.chat.send_action(action="typing")

        processing_msg = update.message.reply_text(
            "🎲 Rolling the dice...\n"
            "Finding you something great! ✨"
        )

        args = context.args or []
        genre_arg = " ".join(args).strip() or None
        pick = get_random_song(user_id=user_id, genre=genre_arg)
        if not pick:
            # Live chart unreachable and no cache — degrade with a clear
            # message instead of crashing on a static-pool fallback.
            processing_msg.edit_text(
                "😓 The live music charts are unreachable right now.\n"
                "Please try /random again in a moment! 🔄"
            )
            return
        artist_name = pick['artist']
        song_name = pick['song']

        artist, song, lyrics, status = search_lyrics_with_fallback(f"{artist_name} {song_name}")

        if not lyrics:
            artist = artist_name
            song = song_name

        # Round 5: canonical display — exactly one clean "Artist - Song".
        # Dedupes repeated artist names ("Rod Wave - Rod Wave - Dope Girl"),
        # strips "(Official Audio)"-style suffixes, normalizes whitespace.
        artist, song = canonicalize_track_names(artist or '', song or '')

        display_title = f"{artist} - {song}" if artist and song else (artist or song or f"{artist_name} - {song_name}")

        lyrics_preview = ""
        if lyrics:
            lyrics_lines = [l.strip() for l in lyrics.strip().split('\n') if l.strip()]
            preview = lyrics_lines[:4]
            lyrics_preview = '\n'.join(f"  {l}" for l in preview)
            if len(lyrics_lines) > 4:
                lyrics_preview += "\n  ..."

        mood = detect_song_mood(lyrics) if lyrics else 'happy'
        mood_emoji = {
            'happy': '😊', 'sad': '😢', 'romantic': '💖',
            'energetic': '⚡', 'relaxed': '😌'
        }.get(mood, '🎵')

        # Run YouTube + recommendations in parallel
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _yt_fut  = _pool.submit(get_youtube_link, artist_name, song_name)
            _rec_fut = _pool.submit(get_similar_songs, artist_name, song_name, mood)
            yt_url = _yt_fut.result()
            recs   = _rec_fut.result()

        yt_section = f"🎬 {yt_url}" if yt_url else ""
        recs_lines = []
        for i, r in enumerate(recs[:3]):
            emoji = ['🔥', '✨', '💫'][i]
            recs_lines.append(f"  {emoji} {r['artist']} — {r['name']}")
        recs_text = '\n'.join(recs_lines) if recs_lines else ""

        parts = [
            f"🎲 Random Pick! 📡 Live from the charts\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎵 {display_title}\n"
            f"  {mood_emoji} Mood: {mood.title()}"
        ]

        if yt_section:
            parts.append(f"\n{yt_section}")

        if lyrics_preview:
            parts.append(f"\n\n📝 Preview:\n{lyrics_preview}")

        if recs_text:
            parts.append(f"\n\n🎵 You might also like:\n{recs_text}")

        parts.append(
            f"\n\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎤 /lyrics {artist_name} {song_name} — full lyrics\n"
            f"🎲 /random — another surprise"
            + (" 🌍" if genre_arg else "")
            + "\n💡 Tip: /random pop, /random afrobeats, /random rock…"
        )

        response = ''.join(parts)
        btn_query = f"{artist} - {song}" if artist and song else display_title
        processing_msg.edit_text(
            response,
            disable_web_page_preview=True,
            reply_markup=song_dashboard_buttons(btn_query),
        )
        logger.info(f"Successfully sent random song to user {user_id}")
        # Round 4: taste stats + milestone badges (local, never breaks picks)
        try:
            log_interaction(user_id, 'random', genre=_safe_genre(artist_name))
            for _bl in _new_badge_lines(user_id):
                update.message.reply_text(_bl, parse_mode='Markdown')
        except Exception as _e:
            logger.debug(f"round4 stats hook failed: {_e}")

    except Exception as e:
        logger.error(f"Error in random command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with random pick.\n"
            "Please try again! 🔄"
        )



# ══════════════════════════════════════════════════════════════════════════
# ROUND 4 — Discovery (mood / extend / about / throwback / newmusic)
#           + Fun (duel / daily / emoji / mystats / badges)
# All heavy logic lives in services/discovery_service.py and
# services/fun_service.py (local-first, APIs are optional enhancement).
# ══════════════════════════════════════════════════════════════════════════

_MOOD_LABELS = {key: label for label, key in MOOD_BUTTONS}


# ── 1. /mood ──────────────────────────────────────────────────────────────

def mood_command(update: Update, context: CallbackContext):
    """Handle /mood — a 5-song mix for the user's mood."""
    user_id = update.effective_user.id
    try:
        text = " ".join(context.args or []).strip()
        if not text:
            update.message.reply_text(
                "🎧 *How are you feeling?*\n"
                "Pick a mood and I'll build you a mix:",
                parse_mode='Markdown',
                reply_markup=mood_buttons(),
            )
            return

        mood = normalize_mood(text)
        if not mood and text.lower() in _MOOD_LABELS:
            mood = text.lower()
        if not mood:
            update.message.reply_text(
                f"🤔 I don't know the mood \"{text}\" yet.\n"
                "Try one of these:",
                reply_markup=mood_buttons(),
            )
            return

        _send_mood_mix(update, user_id, mood)
    except Exception as e:
        logger.error(f"Error in mood command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Couldn't build your mix right now.\n"
            "Please try again! 🔄"
        )


def _send_mood_mix(update, user_id: int, mood: str):
    """Fetch and send a mood mix (works fully offline)."""
    label = _MOOD_LABELS.get(mood, mood.title())
    update.message.chat.send_action(action="typing")
    songs = get_mood_mix(mood, 5)
    if not songs:
        update.message.reply_text(
            "😓 I couldn't put a mix together right now.\n"
            "Please try again! 🔄"
        )
        return

    lines = [f"🎧 *{label} Mix*",
             "━━━━━━━━━━━━━━━━━━━━━", ""]
    for i, s in enumerate(songs, 1):
        lines.append(f"*{i}.* {md(s['artist'])} — {md(s['name'])}")
        if s.get('reason'):
            lines.append(f"   ↳ {s['reason']}")
    lines += ["",
              "━━━━━━━━━━━━━━━━━━━━━",
              "🎧 /mood — another mood  •  🎲 /random — surprise me"]
    try:
        log_interaction(user_id, 'recommend', genre=_safe_genre(songs[0]['artist']))
    except Exception:
        pass
    update.message.reply_text(
        '\n'.join(lines),
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=song_list_buttons(
            [{'artist': s['artist'], 'song': s['name']} for s in songs]
        ),
    )
    logger.info(f"Sent mood mix ({mood}) to user {user_id}")


# ── 2. /extend ────────────────────────────────────────────────────────────

def extend_command(update: Update, context: CallbackContext):
    """Handle /extend — 'finish my playlist' from 3 songs."""
    user_id = update.effective_user.id
    try:
        full = update.message.text or ''
        body = re.sub(r'^/extend(@\w+)?\s*', '', full).strip()

        if body:
            songs = parse_extend_lines(body)
            if songs:
                _send_extend_results(update, user_id, songs,
                                     intro="🎶 Based on your songs")
                return
            # Had text but nothing parseable — ask again properly.
            _pending_extend[user_id] = True
            update.message.reply_text(
                "🤔 I couldn't read any songs there.\n\n"
                "Send me 3 songs, one per line, like this:\n"
                "Tyla - Water\nRema - Calm Down\nAyra Starr - Rush"
            )
            return

        # No songs given — try the user's recent /random history first.
        recent = get_recent_picks(user_id, 3)
        if len(recent) >= 2:
            _send_extend_results(update, user_id, recent,
                                 intro="🎶 Based on your recent random picks")
            return

        _pending_extend[user_id] = True
        update.message.reply_text(
            "🎶 *Finish My Playlist*\n\n"
            "Send me 3 songs you love — one per line, like this:\n"
            "Tyla - Water\nRema - Calm Down\nAyra Starr - Rush\n\n"
            "I'll find 5 more that fit the vibe! ✨",
            parse_mode='Markdown',
        )
    except Exception as e:
        logger.error(f"Error in extend command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


def _handle_extend_songs(update, user_id: int, text: str):
    """Process the song list sent after /extend asked for it."""
    songs = parse_extend_lines(text)
    if not songs:
        update.message.reply_text(
            "🤔 I still couldn't read any songs.\n\n"
            "One per line, like: *Tyla - Water*\n"
            "Or /extend to start over.",
            parse_mode='Markdown',
        )
        return
    _send_extend_results(update, user_id, songs,
                         intro="🎶 Based on your songs")


def _send_extend_results(update, user_id: int, songs: list, intro: str):
    update.message.chat.send_action(action="typing")
    vibe = blend_vibe(songs)
    recs = get_extend_recs(songs, 5)
    if not recs:
        update.message.reply_text(
            "😓 I couldn't find matches for that vibe right now.\n"
            "Please try again! 🔄"
        )
        return

    given = '\n'.join(f"• {md(s['artist'])} - {md(s['song'])}" for s in songs[:5])
    lines = [f"{intro} — *{vibe.get('label', 'your vibe')}*",
             "━━━━━━━━━━━━━━━━━━━━━",
             given,
             "",
             "✨ *Keep the vibe going:*",
             ""]
    for i, r in enumerate(recs, 1):
        lines.append(f"*{i}.* {md(r['artist'])} — {md(r['name'])}")
        if r.get('reason'):
            lines.append(f"   ↳ {r['reason']}")
    lines += ["",
              "━━━━━━━━━━━━━━━━━━━━━",
              "🎶 /extend — try another set"]
    try:
        log_interaction(user_id, 'recommend',
                        genre=vibe.get('genre') or _safe_genre(recs[0]['artist']))
    except Exception:
        pass
    update.message.reply_text(
        '\n'.join(lines),
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=song_list_buttons(
            [{'artist': r['artist'], 'song': r['name']} for r in recs]
        ),
    )
    logger.info(f"Sent extend results ({vibe.get('label')}) to user {user_id}")


# ── 3. /about ─────────────────────────────────────────────────────────────

def about_command(update: Update, context: CallbackContext):
    """Handle /about — find songs by theme/meaning."""
    user_id = update.effective_user.id
    try:
        query = " ".join(context.args or []).strip()
        if not query:
            update.message.reply_text(
                "💭 *Songs about… what?*\n\n"
                "Tell me a theme and I'll find songs that match its meaning:\n"
                "• /about songs about starting over\n"
                "• /about summer nights\n"
                "• /about heartbreak",
                parse_mode='Markdown',
            )
            return

        update.message.chat.send_action(action="typing")
        processing_msg = update.message.reply_text(
            f"💭 Thinking about \"{query}\"… ✨"
        )
        theme = interpret_theme(query)
        songs = match_theme(theme, 5)
        if not songs:
            processing_msg.edit_text(
                "😓 I couldn't find songs for that theme.\n"
                "Try different words! 💭"
            )
            return

        keywords = ', '.join(theme.get('keywords', [])[:5])
        header = f"💭 *Songs about {query}*" if len(query) < 40 else "💭 *Theme match*"
        lines = [header, "━━━━━━━━━━━━━━━━━━━━━", ""]
        if keywords:
            lines.append(f"Reading it as: {keywords}")
            lines.append("")
        for i, s in enumerate(songs, 1):
            lines.append(f"*{i}.* {md(s['artist'])} — {md(s['song'])}")
            if s.get('reason'):
                lines.append(f"   ↳ {s['reason']}")
        lines += ["",
                  "━━━━━━━━━━━━━━━━━━━━━",
                  "💭 /about — try another theme"]
        try:
            genres = theme.get('genres') or []
            log_interaction(user_id, 'recommend',
                            genre=genres[0] if genres else None)
        except Exception:
            pass
        processing_msg.edit_text(
            '\n'.join(lines),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=song_list_buttons(
                [{'artist': s['artist'], 'song': s['song']} for s in songs]
            ),
        )
        logger.info(f"Sent about/theme results to user {user_id}")
    except Exception as e:
        logger.error(f"Error in about command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


# ── 4. /throwback ─────────────────────────────────────────────────────────

def throwback_command(update: Update, context: CallbackContext):
    """Handle /throwback — decade explorer (80s/90s/2000s/2010s)."""
    user_id = update.effective_user.id
    try:
        arg = " ".join(context.args or []).strip()
        if not arg:
            update.message.reply_text(
                "🕺 *Pick a decade!*",
                parse_mode='Markdown',
                reply_markup=decade_buttons(),
            )
            return

        decade = normalize_decade(arg)
        picks = get_throwback(decade, 5)
        if not picks:
            update.message.reply_text(
                "😓 Couldn't dig up that decade right now.\n"
                "Please try again! 🔄"
            )
            return

        decade_emoji = {'80s': '🎸', '90s': '📼',
                        '2000s': '💿', '2010s': '📱'}.get(decade, '🕺')
        lines = [f"{decade_emoji} *{decade} Throwback!*",
                 "━━━━━━━━━━━━━━━━━━━━━", ""]
        for i, s in enumerate(picks, 1):
            lines.append(f"*{i}.* {md(s['artist'])} — {md(s['song'])}")
            if s.get('fact'):
                lines.append(f"   💡 {s['fact']}")
        lines += ["",
                  "━━━━━━━━━━━━━━━━━━━━━",
                  "🕺 /throwback — another decade"]
        update.message.reply_text(
            '\n'.join(lines),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=song_list_buttons(
                [{'artist': s['artist'], 'song': s['song']} for s in picks]
            ),
        )
        logger.info(f"Sent throwback ({decade}) to user {user_id}")
    except Exception as e:
        logger.error(f"Error in throwback command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


# ── 5. /newmusic ──────────────────────────────────────────────────────────

def newmusic_command(update: Update, context: CallbackContext):
    """Handle /newmusic — what's charting right now (honest labeling)."""
    user_id = update.effective_user.id
    try:
        genre = " ".join(context.args or []).strip() or None
        update.message.chat.send_action(action="typing")
        songs, is_live = get_new_music(genre, 5)
        if not songs:
            update.message.reply_text(
                "😓 Couldn't fetch the charts right now.\n"
                "Please try again! 🔄"
            )
            return

        if is_live:
            header = ("🔥 *Hot Right Now*\n"
                      "What everyone's playing on the charts:")
            footer_note = ("\n_Charts update regularly — "
                           "this is what's trending, not release dates._")
        else:
            header = ("🔥 *Hot Right Now*\n"
                      "Popular picks while the live chart refreshes:")
            footer_note = ""
        lines = [header, "━━━━━━━━━━━━━━━━━━━━━", ""]
        rank_emoji = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
        for i, s in enumerate(songs, 1):
            r = rank_emoji[i - 1] if i <= len(rank_emoji) else '🎵'
            lines.append(f"{r} {md(s['artist'])} — {md(s['song'])}")
            if s.get('note'):
                lines.append(f"   ↳ {s['note']}")
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━",
                  "🔥 /newmusic — refresh  •  🎲 /random — surprise me"]
        if footer_note:
            lines.append(footer_note)
        update.message.reply_text(
            '\n'.join(lines),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=song_list_buttons(
                [{'artist': s['artist'], 'song': s['song']} for s in songs]
            ),
        )
        logger.info(f"Sent newmusic (live={is_live}) to user {user_id}")
    except Exception as e:
        logger.error(f"Error in newmusic command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


# ── 6. /duel ──────────────────────────────────────────────────────────────

def _format_duel_question(duel_code: str, idx: int, score: int,
                          total_q: int) -> str:
    questions = get_duel_questions(duel_code)
    q = questions[idx]
    quiz_data = {"total_questions": idx, "score": score}
    return (f"⚔️ *Duel — Question {idx + 1}/{total_q}*\n\n"
            + format_quiz_question(q, quiz_data))


def duel_command(update: Update, context: CallbackContext):
    """Handle /duel — create or join a 5-question quiz duel."""
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "Player"
    chat_id = update.effective_chat.id
    try:
        args = context.args or []
        if args:
            # ── Join a friend's duel ──
            code = args[0].strip().upper()
            duel = join_duel(code, user_id, name)
            if not duel:
                update.message.reply_text(
                    "😕 I couldn't find that duel.\n\n"
                    "Check the code with your friend — it looks like `A3F9K2`.\n"
                    "Or start your own with /duel ⚔️"
                )
                return
            questions = get_duel_questions(code)
            if len(questions) < 3:
                update.message.reply_text(
                    "😓 That duel didn't have enough questions.\n"
                    "Ask your friend to create a new one with /duel ⚔️"
                )
                return
            _duel_chat_ids.setdefault(code, {})[str(user_id)] = chat_id
            active_duel_sessions[user_id] = {
                'code': code, 'idx': 0, 'score': 0,
                'chat_id': chat_id, 'name': name,
            }
            try:
                log_interaction(user_id, 'duel')
            except Exception:
                pass
            update.message.reply_text(
                f"⚔️ *You're in!* Duel vs *{md(duel.get('creator_name', 'your friend'))}*\n"
                "Same 5 questions, most correct wins. Good luck! 🍀\n\n"
                + _format_duel_question(code, 0, 0, len(questions)),
                parse_mode='Markdown',
            )
            logger.info(f"User {user_id} joined duel {code}")
            return

        # ── Create a duel ──
        update.message.reply_text(
            "⚔️ Creating your duel… gathering 5 questions! 🎲"
        )
        duel = create_duel(user_id, name)
        code = duel.get('code', '')
        questions = get_duel_questions(code)
        if len(questions) < 3:
            delete_duel(code)
            update.message.reply_text(
                "😓 I couldn't gather enough questions right now.\n"
                "Please try again in a moment! 🔄"
            )
            return
        _duel_chat_ids.setdefault(code, {})[str(user_id)] = chat_id
        active_duel_sessions[user_id] = {
            'code': code, 'idx': 0, 'score': 0,
            'chat_id': chat_id, 'name': name,
        }
        try:
            log_interaction(user_id, 'duel')
        except Exception:
            pass
        update.message.reply_text(
            f"⚔️ *Duel created!* Your code: `{code}`\n\n"
            "Send the code to a friend — they join with:\n"
            f"/duel {code}\n\n"
            "You'll both answer the same 5 questions. "
            "Most correct answers wins! 🏆\n\n"
            + _format_duel_question(code, 0, 0, len(questions)),
            parse_mode='Markdown',
        )
        logger.info(f"User {user_id} created duel {code}")
    except Exception as e:
        logger.error(f"Error in duel command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


def _handle_duel_answer(update, context, user_id: int, answer: str):
    """Process one A/B/C/D answer inside a duel."""
    sess = active_duel_sessions.get(user_id)
    if not sess:
        return
    try:
        questions = get_duel_questions(sess['code'])
        if sess['idx'] >= len(questions):
            active_duel_sessions.pop(user_id, None)
            return
        q = questions[sess['idx']]
        correct = (ord(answer) - ord('A')) == q.get('answer_index', 0)
        try:
            record_duel_answer(sess['code'], user_id, correct)
        except Exception:
            pass
        if correct:
            sess['score'] += 1
            feedback = "✅ Correct!"
        else:
            feedback = f"❌ Not quite! The answer was: {_correct_display(q)}"
        sess['idx'] += 1

        if sess['idx'] < len(questions):
            update.message.reply_text(
                f"{feedback}\n\n"
                + _format_duel_question(sess['code'], sess['idx'],
                                        sess['score'], len(questions)),
                parse_mode='Markdown',
            )
            return

        # ── Duel finished for this player ──
        active_duel_sessions.pop(user_id, None)
        code = sess['code']
        st = duel_standings(code)
        names = st.get('names', {})
        scores = st.get('scores', {})
        nq = len(questions)

        if not st.get('finished', {}).get(str(user_id)):
            # Opponent hasn't finished yet — wait for them.
            update.message.reply_text(
                f"{feedback}\n\n"
                f"🏁 You finished: *{sess['score']}/{nq}*\n"
                "Waiting for your opponent to finish… ⏳\n"
                "I'll announce the winner as soon as they're done! 🏆",
                parse_mode='Markdown',
            )
            return

        # ── Both finished — declare the winner to both players ──
        players = list(scores.keys())
        if len(players) == 2:
            a, b = players[0], players[1]
            sa, sb = scores.get(a, 0), scores.get(b, 0)
            na, nb = names.get(a, 'Player 1'), names.get(b, 'Player 2')
            winner = st.get('winner')
            if winner == 'tie':
                result = (f"⚔️ *Duel over — it's a TIE!* 🤝\n\n"
                          f"{na}: {sa}/{nq}\n{nb}: {sb}/{nq}")
                winner_id = None
            else:
                wname = names.get(str(winner), 'Winner')
                result = (f"⚔️ *Duel over!* 🏆\n\n"
                          f"{na}: {sa}/{nq}\n{nb}: {sb}/{nq}\n\n"
                          f"🎉 *{wname} wins!*")
                winner_id = int(winner)
        else:
            result = (f"⚔️ *Duel over!*\n\nYour score: *{sess['score']}/{nq}*")
            winner_id = None

        badge_line = ""
        if winner_id:
            badge_line = _award_badge_line(winner_id, 'duel_champ')

        # Tell the finisher…
        update.message.reply_text(
            f"{feedback}\n\n{result}{badge_line}",
            parse_mode='Markdown',
        )
        # …and the opponent (whose chat id we stored at join time).
        try:
            chats = _duel_chat_ids.get(code, {})
            for uid_str, cid in chats.items():
                if int(uid_str) != user_id:
                    context.bot.send_message(
                        chat_id=cid,
                        text=f"{result}{badge_line if int(uid_str) == winner_id else ''}",
                        parse_mode='Markdown',
                    )
        except Exception as e:
            logger.debug(f"duel notify failed: {e}")
        try:
            delete_duel(code)
            _duel_chat_ids.pop(code, None)
        except Exception:
            pass
        logger.info(f"Duel {code} completed, winner={st.get('winner')}")
    except Exception as e:
        logger.error(f"Error in duel answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Try /duel to start over! 🔄"
        )


# ── 7. /daily ─────────────────────────────────────────────────────────────

def daily_command(update: Update, context: CallbackContext):
    """Handle /daily — 5 questions, one play per day, streaks."""
    user_id = update.effective_user.id
    try:
        status = get_daily_status(user_id)
        if not status.get('can_play'):
            update.message.reply_text(
                "✅ You've already played today!\n\n"
                f"🔥 Current streak: *{status.get('streak', 0)}* day(s)\n"
                f"🏆 Best streak: *{status.get('best_streak', 0)}* day(s)\n\n"
                "Come back tomorrow to keep the flame alive! 🔥",
                parse_mode='Markdown',
            )
            return

        questions = make_daily_questions(5)
        if len(questions) < 3:
            update.message.reply_text(
                "😓 I couldn't gather today's questions right now.\n"
                "Please try again in a moment! 🔄"
            )
            return

        active_daily[user_id] = {'questions': questions, 'idx': 0, 'score': 0}
        streak_line = ""
        if status.get('streak', 0) > 0:
            streak_line = f"\n🔥 You're on a *{status['streak']}*-day streak — keep it going!"
        update.message.reply_text(
            "🎯 *Daily Challenge!*\n"
            "5 questions, one play per day." + streak_line + "\n\n"
            + _format_daily_question(user_id),
            parse_mode='Markdown',
        )
        logger.info(f"Started daily challenge for user {user_id}")
    except Exception as e:
        logger.error(f"Error in daily command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


def _format_daily_question(user_id: int) -> str:
    sess = active_daily[user_id]
    q = sess['questions'][sess['idx']]
    quiz_data = {"total_questions": sess['idx'], "score": sess['score']}
    total = len(sess['questions'])
    return (f"🎯 *Daily — Question {sess['idx'] + 1}/{total}*\n\n"
            + format_quiz_question(q, quiz_data))


def _handle_daily_answer(update, context, user_id: int, answer: str):
    """Process one A/B/C/D answer inside the daily challenge."""
    sess = active_daily.get(user_id)
    if not sess:
        return
    try:
        questions = sess['questions']
        q = questions[sess['idx']]
        correct = (ord(answer) - ord('A')) == q.get('answer_index', 0)
        if correct:
            sess['score'] += 1
            feedback = "✅ Correct!"
        else:
            feedback = f"❌ Not quite! The answer was: {_correct_display(q)}"
        sess['idx'] += 1

        if sess['idx'] < len(questions):
            update.message.reply_text(
                f"{feedback}\n\n" + _format_daily_question(user_id),
                parse_mode='Markdown',
            )
            return

        # ── Daily complete ──
        active_daily.pop(user_id, None)
        total = len(questions)
        score = sess['score']
        res = record_daily_play(user_id, score, total)
        try:
            log_interaction(user_id, 'daily')
        except Exception:
            pass
        msg = (f"{feedback}\n\n"
               f"🎯 *Daily complete!* {score}/{total}\n"
               f"🔥 Streak: *{res.get('streak', 0)}* day(s)\n"
               f"🏆 Best: *{res.get('best_streak', 0)}* day(s)")
        if res.get('new_best'):
            msg += "\n✨ New personal best streak!"
        for bl in _new_badge_lines(user_id):
            msg += f"\n{bl}"
        update.message.reply_text(msg, parse_mode='Markdown')
        logger.info(f"Daily complete for user {user_id}: {score}/{total}")
    except Exception as e:
        logger.error(f"Error in daily answer for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Try /daily to start over! 🔄"
        )


# ── 8. /emoji ─────────────────────────────────────────────────────────────

def emoji_command(update: Update, context: CallbackContext):
    """Handle /emoji — guess the song from an emoji rendition."""
    user_id = update.effective_user.id
    try:
        if user_id in active_emoji:
            update.message.reply_text(
                "🎭 You're already playing!\n"
                "Guess the song or type *stop* to end the game.",
                parse_mode='Markdown',
            )
            return
        update.message.chat.send_action(action="typing")
        puzzle = get_emoji_puzzle()
        active_emoji[user_id] = {'puzzle': puzzle, 'score': 0, 'played': 0,
                                 'last_active': time.time()}
        update.message.reply_text(
            "🎭 *Emoji Guessing Game!*\n\n"
            f"{puzzle['emojis']}\n\n"
            "What song is this?\n"
            "Reply with *Artist - Title* (or type *stop* to end).",
            parse_mode='Markdown',
            reply_markup=emoji_exit_buttons(),
        )
        logger.info(f"Started emoji game for user {user_id}")
    except Exception as e:
        logger.error(f"Error in emoji command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


def _handle_emoji_guess(update, user_id: int, text: str):
    """Process one free-text guess inside the emoji game."""
    sess = active_emoji.get(user_id)
    if not sess:
        return
    try:
        if text.lower().strip() in ('stop', 'quit', 'end', 'cancel', '/stop', '/cancel'):
            score, played = sess['score'], sess['played']
            active_emoji.pop(user_id, None)
            update.message.reply_text(
                f"🎭 *Game over!*\n\n"
                f"You guessed *{score}* out of *{played}* right. "
                f"{'🏆 Amazing!' if score >= 5 else 'Nice playing! 🎶'}\n\n"
                "Play again anytime with /emoji!",
                parse_mode='Markdown',
            )
            return

        try:
            log_interaction(user_id, 'emoji')
        except Exception:
            pass
        if check_emoji_guess(sess['puzzle'], text):
            sess['score'] += 1
            sess['played'] += 1
            puzzle = get_emoji_puzzle()
            sess['puzzle'] = puzzle
            update.message.reply_text(
                f"✅ Correct! That's *{text.strip()}*. "
                f"Score: *{sess['score']}* 🎉\n\n"
                f"Next one:\n{puzzle['emojis']}\n\n"
                "What song is this?",
                parse_mode='Markdown',
                reply_markup=emoji_exit_buttons(),
            )
        else:
            update.message.reply_text(
                "❌ Not quite — try again!\n"
                f"Hint: think about what the emojis *mean*. 🤔\n\n"
                f"{sess['puzzle']['emojis']}",
                reply_markup=emoji_exit_buttons(),
            )
    except Exception as e:
        logger.error(f"Error in emoji guess for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Type *stop* to end or /emoji to restart.",
            parse_mode='Markdown',
        )


def emoji_exit_callback(update: Update, context: CallbackContext):
    """Exit the emoji game via its inline '🚪 Exit game' button."""
    user_id = update.effective_user.id
    sess = active_emoji.pop(user_id, None)
    # Via the callback dispatcher, update is a FakeUpdate carrying
    # effective_message (the game message) — no callback_query attribute.
    msg = getattr(update, 'effective_message', None)
    try:
        if msg:
            if sess:
                msg.edit_text(
                    f"🎭 Game over! You got {sess.get('score', 0)} out of "
                    f"{sess.get('played', 0)} right.\n"
                    "Play again anytime with /emoji! 🎶"
                )
            else:
                msg.edit_text("🎭 No active game — type /emoji to play! 🎶")
    except Exception as e:
        logger.warning(f"emoji_exit edit failed: {e}")


def cancel_command(update: Update, context: CallbackContext):
    """Handle /cancel — quit any active game or pending flow."""
    user_id = update.effective_user.id
    cleared = []
    for name, store in (('emoji game', active_emoji),
                        ('quiz', active_quizzes),
                        ('duel', active_duel_sessions),
                        ('daily challenge', active_daily)):
        if user_id in store:
            store.pop(user_id, None)
            cleared.append(name)
    for store in (_pending_recommend_artist, _pending_confirmation,
                  _pending_extend):
        store.pop(user_id, None)
    _mp3_in_progress.discard(
        next((k for k in _mp3_in_progress if k[0] == user_id), None))
    if cleared:
        update.message.reply_text(
            f"🚪 Cancelled: {', '.join(cleared)}.\n\n"
            "What next? /help shows everything I can do! 🎵"
        )
    else:
        update.message.reply_text(
            "Nothing to cancel — you're all clear! 🎵\n"
            "Try /help to see what I can do."
        )


# ── 9. /mystats ───────────────────────────────────────────────────────────

def mystats_command(update: Update, context: CallbackContext):
    """Handle /mystats — the user's music personality."""
    user_id = update.effective_user.id
    try:
        stats = get_music_stats(user_id)
        if not stats.get('total'):
            update.message.reply_text(
                "🌱 *Your taste profile is growing!*\n\n"
                "Use the bot a little — /random, /recommend, /quiz — "
                "and I'll show your music personality here. 🎧",
                parse_mode='Markdown',
            )
            return

        lines = ["🎧 *Your Music Personality*",
                 "━━━━━━━━━━━━━━━━━━━━━", "",
                 stats.get('label', ''), "",
                 "*Top genres:*"]
        for genre, pct in stats.get('top', [])[:3]:
            bar = '🟩' * max(1, pct // 20) + '⬜' * (5 - max(1, pct // 20))
            lines.append(f"• {genre.title()} — {pct}% {bar}")
        lines += ["",
                  f"🎵 Songs explored: *{stats.get('total', 0)}*",
                  f"✅ Quiz correct: *{stats.get('quiz_correct', 0)}*",
                  "",
                  "━━━━━━━━━━━━━━━━━━━━━",
                  "🏅 /badges — see your achievements"]
        update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        logger.info(f"Sent mystats to user {user_id}")
    except Exception as e:
        logger.error(f"Error in mystats command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )


# ── 10. /badges ───────────────────────────────────────────────────────────

def badges_command(update: Update, context: CallbackContext):
    """Handle /badges — earned + locked achievements."""
    user_id = update.effective_user.id
    try:
        ub = get_user_badges(user_id)
        earned = ub.get('earned', [])
        locked = ub.get('locked', [])
        lines = ["🏅 *Your Badges*",
                 "━━━━━━━━━━━━━━━━━━━━━", ""]
        if earned:
            lines.append(f"*Earned ({len(earned)}):*")
            for bid in earned:
                b = BADGES.get(bid, {})
                lines.append(
                    f"{b.get('emoji', '🎖️')} *{b.get('name', bid)}*\n"
                    f"   ↳ {b.get('desc', '')}"
                )
            lines.append("")
        else:
            lines.append("No badges yet — your journey starts now! 🚀")
            lines.append("")
        if locked:
            lines.append(f"*Still to earn ({len(locked)}):*")
            for bid in locked:
                b = BADGES.get(bid, {})
                lines.append(
                    f"🔒 *{b.get('name', bid)}*\n"
                    f"   ↳ {b.get('desc', '')}"
                )
        lines += ["",
                  "━━━━━━━━━━━━━━━━━━━━━",
                  "Play /quiz, /daily and /duel to earn them all! 🎮"]
        update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        logger.info(f"Sent badges to user {user_id}")
    except Exception as e:
        logger.error(f"Error in badges command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong.\n"
            "Please try again! 🔄"
        )
