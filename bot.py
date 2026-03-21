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
from handlers import (
    start_command, help_command, lyrics_command, stats_command,
    recommend_command, quiz_command, quiz_answer, end_quiz_command,
    translate_lyrics_command, youtube_command, analyze_command,
    subscribe_daily_command, unsubscribe_daily_command,
    wiki_command,
    artist_command, trending_command,
    song_command, top_command, random_command,
    natural_language_handler, callback_query_handler
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
logger = logging.getLogger(__name__)

IS_PRODUCTION = os.environ.get('REPLIT_DEPLOYMENT') == '1'

# File that persists the last conflict timestamp across dev process restarts.
# When the Replit workflow restarts bot.py (e.g. after a deploy), the new
# process reads this file and respects the backoff instead of immediately
# competing with production again.
_CONFLICT_STATE_FILE = '/tmp/bot_last_conflict'


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

# ──────────────────────────────────────────────────────────────────────────────
# Shared-DB heartbeat helpers
# ──────────────────────────────────────────────────────────────────────────────
# Production writes a heartbeat row to the shared PostgreSQL database every
# HEARTBEAT_INTERVAL seconds.  Dev reads that row before starting polling;
# if a fresh heartbeat exists, dev never calls getUpdates at all.
#
# This gives a conflict-free architecture by design:
#   - production polls Telegram (normal)
#   - dev reads DB, sees production is active, sleeps — no getUpdates ever
#   - if production goes away (heartbeat stales after HEARTBEAT_TTL seconds),
#     dev can safely start polling again
# ──────────────────────────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL = 90          # production writes heartbeat every 90 s
HEARTBEAT_TTL      = 5 * 60     # dev treats heartbeat fresh for 5 minutes
DEV_RECHECK        = 60         # dev re-reads DB this often (seconds) while sleeping


def _db_conn():
    """Open a short-lived psycopg2 connection.  Returns None on failure."""
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(db_url, connect_timeout=5)
    except Exception as exc:
        logger.debug(f"DB connect failed: {exc}")
        return None


def _ensure_heartbeat_table(conn):
    """Create the heartbeat table if it doesn't exist yet."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_heartbeat (
                id          INTEGER PRIMARY KEY DEFAULT 1,
                environment TEXT        NOT NULL,
                last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                pid         INTEGER
            )
        """)
    conn.commit()


def write_production_heartbeat():
    """Write/refresh the production heartbeat row in the shared DB.

    Called immediately on production startup and then every HEARTBEAT_INTERVAL
    seconds by the scheduler.  Dev instances read this row to learn that
    production is active and must not start polling.
    """
    conn = _db_conn()
    if conn is None:
        return
    try:
        _ensure_heartbeat_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bot_heartbeat (id, environment, last_seen, pid)
                VALUES (1, 'production', NOW(), %s)
                ON CONFLICT (id) DO UPDATE
                    SET environment = 'production',
                        last_seen   = NOW(),
                        pid         = EXCLUDED.pid
            """, (os.getpid(),))
        conn.commit()
        logger.debug("Production heartbeat written to DB.")
    except Exception as exc:
        logger.warning(f"Failed to write production heartbeat: {exc}")
    finally:
        conn.close()


def clear_production_heartbeat():
    """Clear the heartbeat row when production shuts down cleanly."""
    conn = _db_conn()
    if conn is None:
        return
    try:
        _ensure_heartbeat_table(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bot_heartbeat WHERE id = 1")
        conn.commit()
        logger.info("Production heartbeat cleared from DB.")
    except Exception as exc:
        logger.warning(f"Failed to clear production heartbeat: {exc}")
    finally:
        conn.close()


def is_production_active():
    """Return True if a fresh production heartbeat exists in the shared DB.

    Dev instances call this before starting polling and periodically while
    sleeping.  A heartbeat older than HEARTBEAT_TTL is treated as stale
    (production has gone away), allowing dev to resume polling.
    """
    conn = _db_conn()
    if conn is None:
        # Cannot reach DB — conservatively assume production is NOT active
        # so dev can still be used standalone without a DB connection.
        return False
    try:
        _ensure_heartbeat_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM bot_heartbeat
                WHERE id = 1
                  AND environment = 'production'
                  AND last_seen > NOW() - INTERVAL '%s seconds'
            """, (HEARTBEAT_TTL,))
            return cur.fetchone() is not None
    except Exception as exc:
        logger.debug(f"Failed to read production heartbeat: {exc}")
        return False
    finally:
        conn.close()


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
        if IS_PRODUCTION:
            clear_production_heartbeat()

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
                BotCommand("random",      "🎲 Random song discovery"),
                BotCommand("youtube",     "🎬 Find the music video"),
                BotCommand("quiz",        "🎮 Lyrics guessing game"),
                BotCommand("endquiz",     "End current quiz"),
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
                logger.warning(f"Rate limit hit. Waiting {retry_after} seconds")
                time.sleep(retry_after)
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
            if IS_PRODUCTION:
                # Refresh the production heartbeat on a regular schedule so dev
                # instances can see that production is alive without any polling.
                self.scheduler.add_job(
                    write_production_heartbeat,
                    'interval',
                    seconds=HEARTBEAT_INTERVAL,
                    id='heartbeat',
                    replace_existing=True,
                )
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
            dp.add_handler(CommandHandler("analyze",     analyze_command))
            dp.add_handler(CommandHandler("subscribe",   subscribe_daily_command))
            dp.add_handler(CommandHandler("unsubscribe", unsubscribe_daily_command))
            dp.add_handler(CommandHandler("wiki",        wiki_command))
            dp.add_handler(CommandHandler("artist",      artist_command))
            dp.add_handler(CommandHandler("trending",    trending_command))
            dp.add_handler(CommandHandler("song",        song_command))
            dp.add_handler(CommandHandler("top",         top_command))
            dp.add_handler(CommandHandler("random",      random_command))

            dp.add_handler(CallbackQueryHandler(callback_query_handler))
            dp.add_handler(MessageHandler(
                Filters.text & ~Filters.command, natural_language_handler
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
    # Dev gate — never call getUpdates while production is active
    # ──────────────────────────────────────────────────────────────────────────
    # CONFLICT_BACKOFF: seconds dev waits after detecting a conflict before
    # trying to poll again.
    #
    # Architecture note: Replit gives each environment (dev / Reserved-VM) its
    # own database namespace, so the DB heartbeat written by production is not
    # visible to dev.  Instead the conflict error itself is the signal that
    # production is alive.  After one conflict dev backs off 2 hours, and the
    # timestamp is persisted to /tmp/bot_last_conflict so even workflow restarts
    # stay within the backoff window.  Net effect: at most one conflict per
    # 2-hour window — indistinguishable from conflict-free in practice.
    CONFLICT_BACKOFF = 7200  # 2 hours

    def _dev_gate(self):
        """Check DB heartbeat (and recent-conflict backoff) before polling.

        Called at the top of every outer run() loop iteration.
        - If a DB heartbeat shows production is active → sleep until it stales.
        - If a conflict was detected recently → enforce a timed backoff first.
        - Otherwise → return immediately so polling can start.

        This is the core of the conflict-free design: dev never calls
        getUpdates while production holds the heartbeat.  When production runs
        old code without heartbeat support, the backoff limits conflicts to at
        most one per CONFLICT_BACKOFF window instead of every ~34 seconds.
        """
        if IS_PRODUCTION:
            return  # Production skips the gate entirely

        # ── Phase 1: DB heartbeat check ──────────────────────────────────────
        if is_production_active():
            logger.info(
                "Production bot is active (DB heartbeat). "
                "Dev instance will NOT poll — sleeping until production stops."
            )
            while True:
                time.sleep(DEV_RECHECK)
                if not is_production_active():
                    logger.info("Production heartbeat stale — dev resuming polling.")
                    break
                logger.debug("Production still active, dev sleeping…")

        # ── Phase 2: conflict backoff ─────────────────────────────────────────
        # Even if the DB shows no heartbeat (production on old code), back off
        # after a conflict so we do not hammer Telegram every 34 seconds.
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
        if IS_PRODUCTION:
            # Write heartbeat BEFORE starting polling so dev instances see it
            # immediately and never make a competing getUpdates call.
            write_production_heartbeat()
            logger.info("Production heartbeat written — polling will start now.")

        while self.running:
            try:
                # Dev gate: called at the top of EVERY outer loop iteration.
                # This covers startup AND every restart after stopping, so dev
                # can never re-enter polling while production holds a heartbeat.
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
                    allowed_updates=['message', 'callback_query']
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
        if IS_PRODUCTION:
            clear_production_heartbeat()


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
