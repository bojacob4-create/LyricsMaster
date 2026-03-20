import logging
import os
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, MessageHandler, Filters, CommandHandler
from telegram.error import TelegramError
from buttons import (
    lyrics_buttons, song_dashboard_buttons, artist_buttons, artist_summary_buttons,
    recommend_buttons, song_list_buttons, ambiguous_buttons,
    analyze_buttons, stats_buttons, artist_analyze_buttons, recommend_pick_buttons,
    daily_song_buttons, subscribe_count_buttons,
    recommend_results_buttons, daily_picker_buttons
)
from services.lyrics_service import get_song_lyrics
from services.translator_service import (
    translate_to_arabic, translate_text, get_language_code,
    get_language_display, get_supported_languages_text
)
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
)
from services.youtube_service import get_youtube_link, format_youtube_response
from services.youtube_downloader_service import download_youtube_video, download_youtube_audio, download_audio_for_song, cleanup_video
from services.ai_info_service import get_person_info
from services.artist_service import (
    get_artist_info, format_artist_info, get_trending_songs, format_trending,
    get_top_by_genre, format_top_songs, get_available_genres, get_random_song
)
from input_parser import parse_song_query, search_lyrics_with_fallback, clean_input
from intent_router import detect_intent

logger = logging.getLogger(__name__)

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
        "🔍 */analyze* — Deep lyrical breakdown\n"
        "🎤 */artist* — Quick artist profile\n"
        "🔝 */top* — Top songs by genre\n"
        "🎲 */random* — Random song discovery\n"
        "🎬 */youtube* — Find the music video\n"
        "🎮 */quiz* — Lyrics guessing game\n"
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
        "▫️ */random* — Random song discovery\n\n"
        "*🎤 Lyrics & Analysis*\n"
        "▫️ */lyrics* — Get song lyrics\n"
        "▫️ */stats* — Word counts and patterns\n"
        "▫️ */analyze* — Full lyrical breakdown\n"
        "▫️ */translate* — Translate lyrics to any language\n\n"
        "*🎵 Discovery*\n"
        "▫️ */recommend* — Find similar songs\n"
        "▫️ */top* — Top songs by genre\n"
        "▫️ */artist* — Quick artist profile\n"
        "▫️ */youtube* — Find the music video\n"
        "▫️ */wiki* — Artist Wikipedia info\n"
        "▫️ */trending* — Trending songs now\n\n"
        "*🎮 Fun*\n"
        "▫️ */quiz* — Lyrics guessing game (40 songs!)\n"
        "▫️ */endquiz* — End current quiz\n\n"
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


_pending_recommend_artist = {}

# Stores dominant-match confirmation waiting for user's "yes/no" reply.
# Structure: {user_id: {'artist': str, 'song': str, 'intent_cmd': str}}
_pending_confirmation: dict = {}

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


def natural_language_handler(update: Update, context: CallbackContext):
    """Handle non-command text messages via intent detection."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

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
                            + f"\n\nOr type: `Artist - {_seed}` to be more specific."
                        )
                else:
                    _pending_confirmation.pop(user_id, None)
                    _rmsg = (
                        f"🔍 I couldn't find a song called *{_seed}*.\n\n"
                        f"Please use the format: `Artist - Song`\n"
                        f"Example: `Kavinsky - Nightcall`"
                    )
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
            'subscribe': subscribe_daily_command,
            'unsubscribe': unsubscribe_daily_command,
            'wiki': wiki_command,
        }
        handler = handler_map.get(intent)
        if handler:
            handler(update, context)
        else:
            logger.debug(f"Unknown intent '{intent}' for user {user_id}")
        return

    # ── Step 2: Quiz state ───────────────────────────────────────────────────
    quiz_data = active_quizzes.get(user_id)
    if quiz_data and quiz_data.get("state") == "active":
        answer = text.upper()
        if len(answer) == 1 and answer in 'ABCD':
            quiz_answer(update, context)
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
            artist_name = _pending_recommend_artist[user_id]
            from services.lyrics_service import search_song_info
            update.message.chat.send_action(action="typing")
            result = search_song_info(artist_name, text)
            valid = False
            song_query = None
            if result:
                found_artist, found_song, _ = result
                a1 = artist_name.lower().strip()
                a2 = found_artist.lower().strip()
                if a1 in a2 or a2 in a1:
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
                                + f"\n\nOr type: `Artist - {nlp_song}` to be more specific."
                            )
                    else:
                        _pending_confirmation.pop(user_id, None)
                        _rec_msg = (
                            f"🔍 I couldn't find a song called *{nlp_song}*.\n\n"
                            f"Please use the format: `Artist - Song`\n"
                            f"Example: `Kavinsky - Nightcall`"
                        )
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

            update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as nlp_err:
        logger.warning(f"[NLP] Fallback error for user {user_id}: {nlp_err}")


def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    data = query.data
    if ':' not in data:
        return

    action, param = data.split(':', 1)
    user_id = update.effective_user.id
    _pending_recommend_artist.pop(user_id, None)
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
        'artist': artist_command,
        'youtube': youtube_command,
        'mp3': mp3_command,
        'trending': trending_command,
        'translate': translate_lyrics_command,
        'analyze': analyze_command,
        'stats': stats_command,
        'song': song_command,
        'top': top_command,
        'random': random_command,
        'wiki': wiki_command,
        'artistsongs': _artist_songs_picker_command,
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

        update.message.chat.send_action(action="typing")

        if _is_artist_only_query(query):
            clean = clean_input(query)
            info = get_artist_info(clean)
            artist_display = info['name'] if info else clean.title()
            top_songs = _fetch_artist_top_songs(artist_display)
            if top_songs:
                _pending_recommend_artist[user_id] = artist_display
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
        logger.info(f"Successfully sent recommendations to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing recommend command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Oops! Something went wrong while getting recommendations.\n"
            "Please try again in a moment! 🔄"
        )


def _parse_translate_language(query: str):
    match = re.search(r'\s+(?:to|into|in)\s+(\w+)\s*$', query, re.IGNORECASE)
    if match:
        lang_name = match.group(1).strip()
        lang_code = get_language_code(lang_name)
        song_query = query[:match.start()].strip()
        return song_query, lang_code, lang_name
    return query, None, None


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
            response = (
                f"🎵 {display_title}\n"
                f"🌍 {lang_display} Translation:\n\n"
                f"{formatted_lyrics}"
            )
            processing_msg.edit_text(response)
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


def _fetch_artist_top_songs(artist_name: str) -> list:
    info = get_artist_info(artist_name)
    if info:
        return info['top_songs'][:5]

    try:
        api_key = os.environ.get('LASTFM_API_KEY')
        if api_key:
            resp = requests.get(
                'https://ws.audioscrobbler.com/2.0/',
                params={'method': 'artist.getTopTracks', 'artist': artist_name,
                        'api_key': api_key, 'format': 'json', 'limit': 5},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                tracks = data.get('toptracks', {}).get('track', [])
                if tracks:
                    logger.info(f"Last.fm returned {len(tracks)} top tracks for '{artist_name}'")
                    return [t['name'] for t in tracks[:5]]
            logger.warning(f"Last.fm top tracks failed for '{artist_name}': status={resp.status_code}")
        else:
            logger.warning("LASTFM_API_KEY not available for top tracks lookup")
    except Exception as e:
        logger.warning(f"Last.fm top tracks error for '{artist_name}': {e}")

    try:
        resp = requests.get(
            'https://itunes.apple.com/search',
            params={'term': artist_name, 'media': 'music', 'entity': 'song', 'limit': 50},
            timeout=5
        )
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            seen = set()
            songs = []
            artist_lower = artist_name.lower()
            artist_words = set(artist_lower.split())
            for r in results:
                aname = (r.get('artistName') or '').lower()
                tname = r.get('trackName', '')
                if not tname or tname in seen:
                    continue
                aname_words = set(aname.replace(',', ' ').replace('&', ' ').split())
                if artist_lower in aname or artist_words <= aname_words:
                    seen.add(tname)
                    songs.append(tname)
                    if len(songs) >= 5:
                        break
            if songs:
                logger.info(f"iTunes returned {len(songs)} tracks for '{artist_name}'")
                return songs
    except Exception as e:
        logger.warning(f"iTunes fallback error for '{artist_name}': {e}")

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

def mp3_command(update: Update, context: CallbackContext):
    """Handle the MP3 button — convert a known song to MP3."""
    user_id = update.effective_user.id
    try:
        if not context.args:
            update.message.reply_text(
                "🎧 Use the MP3 button on any song result to get the audio file."
            )
            return

        raw = " ".join(context.args)
        logger.info(f"User {user_id} requested MP3: '{raw}'")

        processing_message = update.message.reply_text(
            "🎧 Converting to MP3...\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⏳ Finding audio source and converting.\n"
            "This may take 30–60 seconds."
        )

        if ' - ' in raw:
            parts = raw.split(' - ', 1)
            artist_q, song_q = parts[0].strip(), parts[1].strip()
        else:
            artist_q, song_q = raw.strip(), ''

        success, result = download_audio_for_song(artist_q, song_q)

        if success:
            file_path, info_message, title, uploader = result
            processing_message.edit_text(info_message)
            try:
                with open(file_path, 'rb') as audio_file:
                    update.message.reply_audio(
                        audio_file,
                        caption=f"🎵 {title}",
                        title=title,
                        performer=uploader
                    )
            except Exception as send_err:
                logger.error(f"Failed to send audio: {send_err}")
                processing_message.edit_text(
                    "❌ The MP3 was created but couldn't be sent.\n"
                    "It may be too large for Telegram (50MB limit)."
                )
            cleanup_video(file_path)
        else:
            processing_message.edit_text(result)

    except Exception as e:
        logger.error(f"Error in mp3 command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with the MP3 conversion.\n"
            "Please try again later! 🔄"
        )


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
            ('afrobeat', 'Afrobeats'), ('reggae', 'Reggae'), ('k-pop', 'K-Pop'),
            ('kpop', 'K-Pop'), ('amapiano', 'Amapiano'),
        ]
        extract_lower = extract[:500].lower()
        found_genres = []
        for pattern, label in genre_patterns:
            if pattern in extract_lower or pattern in desc:
                if label not in found_genres:
                    found_genres.append(label)
        if found_genres:
            genre = ' / '.join(found_genres[:2])

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
        for pattern, label in country_patterns:
            if pattern in desc or pattern in extract_lower:
                country = label
                break

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
            update.message.reply_text(format_artist_info(info), reply_markup=artist_buttons(info['name'], info.get('top_songs', [])))
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
    markup = artist_summary_buttons(info['name'], info['top_songs'][:5])
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

        pick = get_random_song()
        artist_name = pick['artist']
        song_name = pick['song']

        artist, song, lyrics, status = search_lyrics_with_fallback(f"{artist_name} {song_name}")

        if not lyrics:
            artist = artist_name
            song = song_name

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
            f"🎲 Random Pick!\n"
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
            f"🎲 /random — try another!"
        )

        response = ''.join(parts)
        processing_msg.edit_text(response, disable_web_page_preview=True)
        logger.info(f"Successfully sent random song to user {user_id}")

    except Exception as e:
        logger.error(f"Error in random command for user {user_id}: {str(e)}")
        update.message.reply_text(
            "😓 Something went wrong with random pick.\n"
            "Please try again! 🔄"
        )

