import logging
import os
import sys
import time
import signal
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, BotCommand
from telegram.ext import (
    CallbackContext,
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters
)
from telegram.error import (
    TelegramError,
    NetworkError,
    TimedOut,
    RetryAfter
)
from log_redaction import install_secret_redaction
from handlers import (
    start_command, help_command, lyrics_command, stats_command,
    recommend_command, quiz_command, quiz_answer, end_quiz_command,
    translate_lyrics_command, youtube_command, analyze_command,
    subscribe_daily_command, unsubscribe_daily_command,
    wiki_command,
    artist_command, trending_command,
    song_command, top_command, random_command, playlist_command,
    natural_language_handler, callback_query_handler,
    unknown_command_handler, cancel_command,
    # Round 4: discovery + fun
    mood_command, extend_command, about_command, throwback_command,
    newmusic_command, duel_command, daily_command, emoji_command,
    mystats_command, badges_command,
    mp3_retry_tick, video_retry_tick,
    worker_channel_post, worker_timeout_tick,
    # Round 15: /mp3 and /download are real slash commands now
    # (previously callback/NL-only, so "/mp3" looped "Did you mean /mp3?").
    mp3_command, download_command,
)
from services.daily_song_service import send_daily_song

# Configure logging with both console and file handlers
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
# Never let secrets (bot token, API keys) reach the logs — redacts rendered
# records, tracebacks, and uncaught-exception output.
install_secret_redaction()
logger = logging.getLogger(__name__)

IS_PRODUCTION = os.environ.get('REPLIT_DEPLOYMENT') == '1'

# Owner's Telegram chat id — used only for critical self-alerts (round 63:
# getUpdates Conflict). A Conflict is silent by default: the bot just misses
# messages. The owner needs to know, because it means a second instance
# (e.g. the old Replit copy) is polling with the same token.
OWNER_CHAT_ID = os.environ.get('OWNER_CHAT_ID', '').strip()

# File that persists the last conflict timestamp across dev process restarts.
# When the Replit workflow restarts bot.py (e.g. after a deploy), the new
# process reads this file and respects the backoff instead of immediately
# competing with production again.
_CONFLICT_STATE_FILE = '/tmp/bot_last_conflict'

# Throttle for the owner Conflict DM (round 63): a prolonged two-instance
# fight re-triggers the alert on every backoff cycle — at most one DM here.
_CONFLICT_ALERT_FILE = '/tmp/bot_last_conflict_alert'
_CONFLICT_ALERT_THROTTLE = 1800  # seconds


def _read_conflict_time() -> float:
    """Return epoch time of last recorded conflict, or 0 if none."""
    try:
        with open(_CONFLICT_STATE_FILE) as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def _write_conflict_time(t: float):
    """Persist the conflict timestamp so restarts honour the backoff."""
    try:
        with open(_CONFLICT_STATE_FILE, 'w') as f:
            f.write(str(t))
    except Exception:
        pass


# Liveness file the watchdog checks. The worker rewrites it every minute via
# the scheduler below; a missing or stale file means the worker vanished
# silently or is frozen (process-name checks alone can't see that).
_HEARTBEAT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    '.heartbeat')


def _write_heartbeat():
    """Rewrite the liveness file; failures must never disturb the bot."""
    try:
        with open(_HEARTBEAT_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass



class TelegramBotWorker:
    def __init__(self, token):
        self.token = token
        self.updater = None
        self.retry_count = 0
        self.max_retries = 5
        self.retry_delay = 60
        self.last_keepalive = time.time()
        self.keepalive_interval = 300
        self.running = True
        self.scheduler = None
        # Epoch seconds of the most recent conflict — read from disk so it
        # survives process restarts (Replit workflow restarts bot.py on crash).
        self._last_conflict_at = _read_conflict_time()

        logger.info("Bot worker initialized with monitor logging")

        signal.signal(signal.SIGINT,  self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
        if self.updater:
            self.updater.stop()

    def setup_commands(self):
        """Set up bot commands menu."""
        try:
            commands = [
                BotCommand("start",       "Welcome & overview"),
                BotCommand("help",        "Full command guide"),
                BotCommand("song",        "🎵 Full song dashboard"),
                BotCommand("lyrics",      "🎤 Get song lyrics"),
                BotCommand("stats",       "📊 Song word statistics"),
                BotCommand("recommend",   "🎵 Find similar songs"),
                BotCommand("analyze",     "🔍 Deep lyrical analysis"),
                BotCommand("translate",   "🌍 Translate lyrics to any language"),
                BotCommand("artist",      "🎤 Quick artist profile"),
                BotCommand("top",         "🔝 Top songs by genre"),
                BotCommand("playlist",    "🎧 Artist playlist: all-time + new + trending"),
                BotCommand("random",      "🎲 Random song discovery"),
                BotCommand("youtube",     "🎬 Find the music video"),
                BotCommand("mp3",         "🎧 Get the song as an MP3"),
                BotCommand("download",    "📥 Download a YouTube video"),
                BotCommand("quiz",        "🎮 Lyrics guessing game"),
                BotCommand("endquiz",     "End current quiz"),
                BotCommand("mood",        "🎧 Mix for your mood"),
                BotCommand("extend",      "🎶 Finish my playlist"),
                BotCommand("about",       "💭 Find songs by theme"),
                BotCommand("throwback",   "🕺 Decade throwbacks"),
                BotCommand("newmusic",    "🔥 What's hot right now"),
                BotCommand("duel",        "⚔️ Quiz duel with a friend"),
                BotCommand("daily",       "🎯 Daily challenge"),
                BotCommand("emoji",       "🎭 Emoji song guessing"),
                BotCommand("mystats",     "🎧 Your music personality"),
                BotCommand("badges",      "🏅 Your achievements"),
                BotCommand("wiki",        "📚 Artist Wikipedia info"),
                BotCommand("trending",    "📈 Trending songs now"),
                BotCommand("subscribe",   "🔔 Daily song picks"),
                BotCommand("unsubscribe", "Stop daily updates"),
            ]
            self.updater.bot.set_my_commands(commands)
            logger.info("Bot commands menu set up successfully")
        except Exception as e:
            logger.error(f"Failed to set up bot commands: {str(e)}")

    def error_handler(self, update: Update, context: CallbackContext):
        """Handle bot errors."""
        try:
            error_str = str(context.error)

            # Conflict = another instance is polling. In dev mode this means
            # production just started. Stop immediately — don't wait for the
            # keepalive timer; that window is where conflicts happen.
            if 'Conflict' in error_str and 'getUpdates' in error_str:
                if not IS_PRODUCTION:
                    now = time.time()
                    self._last_conflict_at = now
                    _write_conflict_time(now)   # survive process restarts
                    logger.info(
                        "Conflict detected — production bot is now active. "
                        "Dev instance stopping polling immediately."
                    )
                    self._stop_polling()
                # Round 63: never suffer a two-instance fight silently. A
                # Conflict means messages are being missed right now — the
                # owner has to know (old Replit copy still alive?).
                self._maybe_alert_owner_conflict()
                return

            if isinstance(context.error, NetworkError):
                logger.warning(f"Network error: {error_str}")
                self.handle_connection_error()
                return
            elif isinstance(context.error, TimedOut):
                logger.warning("Request timed out")
                self.handle_connection_error()
                return
            elif isinstance(context.error, RetryAfter):
                retry_after = context.error.retry_after
                # Never sleep on a dispatcher worker thread — a burst of
                # rate limits would park every worker and silence the bot
                # for everyone. PTB's request layer already backs off; we
                # just log and let the next poll proceed normally.
                logger.warning(
                    f"Rate limit hit (retry_after={retry_after}s); "
                    "not sleeping on dispatcher thread")
                return
            else:
                logger.error(f"Update {update} caused error: {context.error}")

            if update and update.effective_message:
                update.effective_message.reply_text(
                    "😓 Something went wrong. Please try again in a moment! 🔄"
                )
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}")

    def _stop_polling(self):
        """Stop the updater's polling thread (dev use only)."""
        try:
            if self.updater:
                self.updater.stop()
        except Exception:
            pass

    def _maybe_alert_owner_conflict(self):
        """DM the owner when another instance polls with our token (round 63).

        A getUpdates Conflict is otherwise silent — the bot just misses
        messages while the two instances fight. Throttled so a prolonged
        fight doesn't spam: at most one DM per _CONFLICT_ALERT_THROTTLE.
        """
        try:
            if not OWNER_CHAT_ID or not self.updater:
                return
            now = time.time()
            try:
                with open(_CONFLICT_ALERT_FILE) as f:
                    last = float(f.read().strip())
            except Exception:
                last = 0.0
            if now - last < _CONFLICT_ALERT_THROTTLE:
                return
            self.updater.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=("⚠️ Another copy of me just started polling with the same token, "
                      "so I've paused to avoid a fight over your messages.\n\n"
                      "If that's your old Replit copy, stop it there and I'll resume on my own. "
                      "If you don't recognize it, tell Pex — the token may need rotating."))
            with open(_CONFLICT_ALERT_FILE, 'w') as f:
                f.write(str(now))
            logger.info("Conflict owner alert sent")
        except Exception as e:
            logger.error(f"Conflict owner alert failed: {e}")

    def handle_connection_error(self):
        """Handle connection errors with exponential backoff."""
        wait_time = min(300, self.retry_delay * (2 ** self.retry_count))
        logger.info(f"Connection error, waiting {wait_time}s before retry...")
        time.sleep(wait_time)
        self.retry_count += 1

    def keepalive(self):
        """Perform keepalive tasks."""
        current_time = time.time()
        if current_time - self.last_keepalive >= self.keepalive_interval:
            try:
                self.updater.bot.get_me()
                logger.debug("Keepalive check successful")
                self.last_keepalive = current_time
                self.retry_count = 0
            except Exception as e:
                logger.warning(f"Keepalive check failed: {str(e)}")
                self.handle_connection_error()

    def _setup_daily_scheduler(self):
        try:
            if self.scheduler:
                try:
                    self.scheduler.shutdown(wait=False)
                except Exception:
                    pass
            import pytz
            utc = pytz.UTC
            self.scheduler = BackgroundScheduler(timezone=utc)
            self.scheduler.add_job(
                self._send_daily_wrapper,
                'cron',
                hour=9,
                minute=0,
                id='daily_song',
                replace_existing=True,
                misfire_grace_time=3600
            )
            # Liveness heartbeat for the watchdog (see _HEARTBEAT_FILE).
            self.scheduler.add_job(
                _write_heartbeat,
                'interval',
                minutes=1,
                id='heartbeat',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120
            )
            # MP3 retry queue: every 5 min, retry queued block-wave failures.
            self.scheduler.add_job(
                self._mp3_retry_wrapper,
                'interval',
                minutes=5,
                id='mp3_retry',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300
            )
            # Video retry queue (round 17): every 5 min, retry queued
            # /download block-wave failures.
            self.scheduler.add_job(
                self._video_retry_wrapper,
                'interval',
                minutes=5,
                id='video_retry',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300
            )
            # Home-worker timeout (round 34): every 2 min, fall back
            # locally for jobs the streamer never answered (offline /
            # crashed / asleep).
            self.scheduler.add_job(
                self._worker_timeout_wrapper,
                'interval',
                minutes=2,
                id='worker_timeout',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120
            )
            _write_heartbeat()
            self.scheduler.start()
            logger.info("Daily song scheduler started (09:00 UTC)")
        except Exception as e:
            logger.error(f"Failed to set up daily scheduler: {e}")

    def _send_daily_wrapper(self):
        try:
            if self.updater and self.updater.bot:
                class BotContext:
                    def __init__(self, bot):
                        self.bot = bot
                send_daily_song(BotContext(self.updater.bot))
        except Exception as e:
            logger.error(f"Error in daily song delivery: {e}")

    def _mp3_retry_wrapper(self):
        try:
            if self.updater and self.updater.bot:
                mp3_retry_tick(self.updater.bot)
        except Exception as e:
            logger.error(f"Error in MP3 retry tick: {e}")

    def _video_retry_wrapper(self):
        try:
            if self.updater and self.updater.bot:
                video_retry_tick(self.updater.bot)
        except Exception as e:
            logger.error(f"Error in video retry tick: {e}")

    def _worker_timeout_wrapper(self):
        try:
            if self.updater and self.updater.bot:
                worker_timeout_tick(self.updater.bot)
        except Exception as e:
            logger.error(f"Error in worker timeout tick: {e}")

    def initialize(self):
        """Initialize the bot with handlers."""
        try:
            self.updater = Updater(
                token=self.token,
                use_context=True,
                request_kwargs={
                    'read_timeout': 30,
                    'connect_timeout': 30
                }
            )

            self.updater.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook cleared, ready for polling")

            dp = self.updater.dispatcher

            dp.add_handler(CommandHandler("start",       start_command))
            dp.add_handler(CommandHandler("help",        help_command))
            dp.add_handler(CommandHandler("lyrics",      lyrics_command))
            dp.add_handler(CommandHandler("stats",       stats_command))
            dp.add_handler(CommandHandler("recommend",   recommend_command))
            dp.add_handler(CommandHandler("quiz",        quiz_command))
            dp.add_handler(CommandHandler("endquiz",     end_quiz_command))
            dp.add_handler(CommandHandler("translate",   translate_lyrics_command))
            dp.add_handler(CommandHandler("youtube",     youtube_command))
            dp.add_handler(CommandHandler("mp3",         mp3_command))
            dp.add_handler(CommandHandler("download",    download_command))
            dp.add_handler(CommandHandler("analyze",     analyze_command))
            dp.add_handler(CommandHandler("subscribe",   subscribe_daily_command))
            dp.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
            dp.add_handler(CommandHandler("wiki",        wiki_command))
            dp.add_handler(CommandHandler("artist",      artist_command))
            dp.add_handler(CommandHandler("trending",    trending_command))
            dp.add_handler(CommandHandler("song",        song_command))
            dp.add_handler(CommandHandler("top",         top_command))
            dp.add_handler(CommandHandler("playlist",    playlist_command))
            dp.add_handler(CommandHandler("random",      random_command))
            # Round 4: discovery + fun
            dp.add_handler(CommandHandler("mood",        mood_command))
            dp.add_handler(CommandHandler("extend",      extend_command))
            dp.add_handler(CommandHandler("about",       about_command))
            dp.add_handler(CommandHandler("throwback",   throwback_command))
            dp.add_handler(CommandHandler("newmusic",    newmusic_command))
            dp.add_handler(CommandHandler("duel",        duel_command))
            dp.add_handler(CommandHandler("daily",       daily_command))
            dp.add_handler(CommandHandler("emoji",       emoji_command))
            dp.add_handler(CommandHandler("mystats",     mystats_command))
            dp.add_handler(CommandHandler("badges",      badges_command))
            dp.add_handler(CommandHandler("cancel",      cancel_command))

            dp.add_handler(CallbackQueryHandler(callback_query_handler))
            # Home worker DONE/FAIL signals arrive as channel posts from
            # the private worker channel (round 34).
            dp.add_handler(MessageHandler(
                Filters.update.channel_post, worker_channel_post))
            dp.add_handler(MessageHandler(
                Filters.text & ~Filters.command, natural_language_handler
            ))
            # Catch-all for mistyped commands (must be last): without this,
            # "/strt" gets total silence and the bot looks dead.
            dp.add_handler(MessageHandler(
                Filters.command, unknown_command_handler
            ))

            dp.add_error_handler(self.error_handler)

            self.setup_commands()
            self._setup_daily_scheduler()

            logger.info("Bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize bot: {str(e)}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Dev backs off 2 hours after a conflict so dev and production never
    # poll Telegram simultaneously.  The timestamp is persisted to disk so
    # restarts stay within the backoff window.
    CONFLICT_BACKOFF = 7200  # 2 hours

    def _dev_gate(self):
        """Enforce conflict backoff before polling.

        Called at the top of every outer run() loop iteration.
        After a conflict is detected, dev backs off for CONFLICT_BACKOFF seconds
        so dev and production never poll Telegram simultaneously.
        """
        if IS_PRODUCTION:
            return  # Production skips the gate entirely

        elapsed = time.time() - self._last_conflict_at
        if self._last_conflict_at > 0 and elapsed < self.CONFLICT_BACKOFF:
            wait = self.CONFLICT_BACKOFF - elapsed
            resume_at = time.strftime(
                '%H:%M UTC', time.gmtime(self._last_conflict_at + self.CONFLICT_BACKOFF)
            )
            logger.info(
                f"Production conflict on record — dev backing off {wait/60:.1f} min "
                f"(until ~{resume_at}). Production handles all traffic in this window."
            )
            time.sleep(wait)

        logger.info("Dev gate cleared — starting polling.")

    def run(self):
        """Run the bot with automatic reconnection and keepalive."""
        while self.running:
            try:
                # Dev gate: called at the top of EVERY outer loop iteration
                # to enforce the conflict backoff window.
                if not IS_PRODUCTION:
                    self._dev_gate()

                if not self.initialize():
                    if self.retry_count >= self.max_retries:
                        logger.error("Max retries reached. Exiting…")
                        sys.exit(1)

                    self.retry_count += 1
                    wait_time = self.retry_delay * (2 ** (self.retry_count - 1))
                    logger.info(
                        f"Retrying initialization in {wait_time}s… "
                        f"(Attempt {self.retry_count}/{self.max_retries})"
                    )
                    time.sleep(wait_time)
                    continue

                self.retry_count = 0
                self.last_keepalive = time.time()

                logger.info("Starting bot polling…")

                self.updater.start_polling(
                    drop_pending_updates=True,
                    timeout=30,
                    read_latency=1.0,
                    allowed_updates=['message', 'callback_query', 'channel_post']
                )

                logger.info("Bot is running successfully")

                while self.running and self.updater.running:
                    self.keepalive()
                    time.sleep(10)

            except Exception as e:
                logger.error(f"Bot crashed: {str(e)}")
                if self.updater:
                    try:
                        self.updater.stop()
                    except Exception:
                        pass
                self.updater = None

                if self.retry_count >= self.max_retries:
                    logger.error("Max retries reached. Exiting…")
                    sys.exit(1)

                self.retry_count += 1
                wait_time = self.retry_delay * (2 ** (self.retry_count - 1))
                logger.info(
                    f"Restarting bot in {wait_time}s… "
                    f"(Attempt {self.retry_count}/{self.max_retries})"
                )
                time.sleep(wait_time)

        logger.info("Bot shutdown complete")


def main():
    """Entry point for the bot worker."""
    try:
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN not found in environment variables")

        bot_worker = TelegramBotWorker(token)
        bot_worker.run()

    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
