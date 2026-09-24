"""Home-worker bridge: offload /download to the user's home streamer. 🏠

The user's spare Google TV Streamer (Termux + worker.py) downloads YouTube
videos over the HOME internet connection — a residential IP YouTube doesn't
block — instead of this datacenter machine, whose IP gets block-waved.

Telegram is the message bus (no open ports; the streamer sits behind NAT):

  server --JOB--> channel C --video + DONE--> server --copyMessage--> user
         (MAIN token)      (WORKER token)              (MAIN token)

Token direction matters: Telegram's getUpdates NEVER delivers a bot its own
messages, so each side posts with the token the OTHER side polls:
  * JOB notes are posted with the MAIN token → the worker (polling the
    WORKER token) receives them as another bot's channel post.
  * The worker uploads the video to channel C with the WORKER token, then
    posts DONE <job_id> <video_message_id> (WORKER token) → this bot
    (polling the MAIN token) receives both via its channel_post handler.
  * The server delivers to the user with copyMessage (MAIN token) — the
    MAIN token never leaves the server; the streamer only ever holds the
    WORKER token.

Security: the worker only acts on posts in channel C (it checks chat.id),
and the server only accepts DONE/FAIL from channel C. No extra shared
secret is needed — only holders of the two bot tokens can post to or read
from the private channel, and the main token lives only on this server.

If the worker is offline, jobs sit pending and worker_timeout_tick()
(2-min scheduler job) falls back to the local download path after
_WORKER_TIMEOUT_SECS — the user never has to tap again either way.
"""

import json
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)

# How long to wait for the worker's DONE/FAIL before falling back locally.
# 4 minutes: a healthy worker finishes in ~1-2 min, so this only fires when
# the streamer is offline/wedged — and the user asked for a fast bot.
_WORKER_TIMEOUT_SECS = 240

_JOB_STORE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "worker_jobs.json",
)

# Honest notices for permanent worker failures (mirrors the wording the
# local download path uses — no ❌, per house style).
HONEST_FAIL_MSGS = {
    "too_long": (
        "😕 Video Too Long\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Max duration: 10 minutes.\n"
        "Try a shorter video."
    ),
    "too_large": (
        "😕 File Too Large\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "The video is over Telegram's 50MB limit.\n"
        "Try a shorter video."
    ),
    # Round-35: audio jobs get track wording, never the video notices.
    "audio_too_long": (
        "😕 Track Too Long\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Max duration: 10 minutes.\n"
        "Try a shorter track."
    ),
    "audio_too_large": (
        "😕 File Too Large\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "The audio is over Telegram's 50MB limit.\n"
        "Try a shorter track."
    ),
}


def _env(name, default=""):
    return os.environ.get(name, default) or default


def worker_enabled():
    """True when the home-worker bridge is configured. Read dynamically so
    tests (and a future no-restart toggle) can flip it via the environment.

    Only the channel id is required: the server never calls the API with
    the WORKER token (JOBs go out under the MAIN token, delivery is via
    copyMessage under the MAIN token), so the worker token lives only on
    the streamer — never on this server.
    """
    return bool(_env("WORKER_CHANNEL_ID"))


def _worker_channel_id():
    try:
        return int(_env("WORKER_CHANNEL_ID"))
    except (ValueError, TypeError):
        return 0


# ------------------------------------------------------------------ store ---
def _load_jobs():
    try:
        with open(_JOB_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _job_update(job_id, entry):
    """Upsert one job record. Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            data[job_id] = entry
            # keep the file small — drop terminal records older than a day
            cutoff = time.time() - 86400
            for k in [k for k, v in data.items()
                      if v.get("status") in ("done", "failed", "expired")
                      and v.get("ts", 0) < cutoff]:
                data.pop(k, None)
            return data

        locked_json_update(_JOB_STORE, _update)
    except Exception:
        pass


# ------------------------------------------------------------- heartbeat ---
# Round-37: the worker posts "HB <unix_ts>" every 60s. When heartbeats go
# stale the streamer is offline/rebooting — the bot then skips the worker
# instantly instead of burning the 4-minute timeout on every request.
_HB_STORE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "worker_heartbeat.json",
)
_HEARTBEAT_MAX_AGE_SECS = 180


def note_heartbeat(ts=None):
    """Record a worker heartbeat. Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            data["ts"] = ts or time.time()
            return data

        locked_json_update(_HB_STORE, _update)
    except Exception:
        pass


def last_heartbeat():
    """Unix timestamp of the last recorded heartbeat, or 0. Never raises."""
    try:
        with open(_HB_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = float(data.get("ts", 0)) if isinstance(data, dict) else 0
        return ts if ts > 0 else 0
    except Exception:
        return 0


def worker_alive():
    """True when the streamer recently proved it's alive.

    A streamer that never sent a heartbeat (fresh install, older worker)
    counts as alive — the 4-minute timeout remains the safety net there.
    Only a heartbeat gone stale marks it dead, so the bot skips the
    worker instantly instead of stalling the user. Never raises.
    """
    try:
        if not worker_enabled():
            return False
        ts = last_heartbeat()
        if not ts:
            return True
        return (time.time() - ts) <= _HEARTBEAT_MAX_AGE_SECS
    except Exception:
        return True


# ------------------------------------------------------------------- bus ---
def _api_send_message(token, chat_id, text):
    """POST sendMessage. Returns True on ok. Never raises."""
    try:
        import requests  # lazy: keeps the module import-light for tests
        r = requests.post(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data={"chat_id": chat_id, "text": text},
            timeout=20,
        )
        return bool(r.json().get("ok"))
    except Exception as e:
        logger.warning("[WORKER] sendMessage failed: %s", type(e).__name__)
        return False


def post_job(chat_id, user_id, url, title="", kind="video",
             artist="", song="", expected_dur=0):
    """Hand a /download (video) or /mp3 (audio, round-35) to the home worker.

    Posts 'JOB {...}' to the worker channel with the MAIN token (the worker
    polls the WORKER token, so it receives this as another bot's post) and
    records the job as pending. artist/song ride along for audio jobs so
    the DONE handler can cache the delivered file_id. Round-37: url may be
    "" for audio jobs (server block wave) — the worker resolves the
    YouTube URL itself over the home connection; expected_dur (seconds,
    from lrclib) helps it pick the original recording. Returns the job_id,
    or None when the bridge is disabled/unreachable — the caller then uses
    the local path. Never raises.
    """
    try:
        if not worker_enabled():
            return None
        if kind not in ("video", "audio"):
            kind = "video"
        try:
            expected_dur = int(expected_dur or 0)
        except Exception:
            expected_dur = 0
        job_id = uuid.uuid4().hex[:12]
        payload = {"job_id": job_id, "chat_id": chat_id, "user_id": user_id,
                   "video_url": url or "", "title": (title or "")[:200],
                   "kind": kind,
                   "artist": (artist or "")[:200], "song": (song or "")[:200],
                   "expected_dur": expected_dur,
                   "requested_at": time.time()}
        text = "JOB " + json.dumps(payload, separators=(",", ":"))
        if not _api_send_message(_env("TELEGRAM_TOKEN"), _worker_channel_id(),
                                 text):
            return None
        _job_update(job_id, dict(payload, ts=time.time(), status="pending"))
        logger.info("[WORKER][QUEUED] job %s → chat %s: %s",
                    job_id, chat_id, url or "<worker resolves>")
        return job_id
    except Exception as e:
        logger.warning("[WORKER] post_job failed: %s", type(e).__name__)
        return None


def parse_channel_signal(text):
    """Parse a worker signal post.

    Returns ("done", job_id, message_id), ("fail", job_id, code), or None
    for anything else (JOB echoes, human chatter, malformed signals).
    Never raises.
    """
    try:
        if not isinstance(text, str):
            return None
        t = text.strip()
        if t.startswith("DONE "):
            parts = t[5:].split()
            if len(parts) != 2 or not parts[0]:
                return None
            try:
                message_id = int(parts[1])
            except (ValueError, TypeError):
                return None
            if message_id <= 0:
                return None
            return ("done", parts[0], message_id)
        if t.startswith("FAIL "):
            rest = t[5:].strip()
            if not rest:
                return None
            parts = rest.split(None, 1)
            code = parts[1] if len(parts) > 1 else "error"
            return ("fail", parts[0], code)
        return None
    except Exception:
        return None


# Caption the user sees on the delivered video (same wording the local
# download path uses).
COPY_CAPTION = "🎉 Here's your video!"


def get_job_entry(job_id):
    """Return the stored job entry dict (any status), or None. Round-35:
    the DONE handler reads artist/song/kind for audio jobs. Never raises.
    """
    try:
        entry = _load_jobs().get(job_id)
        return dict(entry) if isinstance(entry, dict) else None
    except Exception:
        return None


def build_copy_params(job_id, message_id):
    """Params for the server's copyMessage delivery of a worker upload.

    Returns {"chat_id", "from_chat_id", "message_id", "caption"} for the
    Bot API copyMessage call (made with the MAIN token), or None when the
    job is unknown or already handled. Never raises.
    """
    try:
        entry = _load_jobs().get(job_id)
        if not isinstance(entry, dict) or entry.get("status") != "pending":
            return None
        chat_id = entry.get("chat_id")
        # bool is a subclass of int — reject True/False explicitly
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return None
        mid = int(message_id)
        if mid <= 0:
            return None
        # Round-37b: audio deliveries get the MP3 caption — never the
        # video one.
        caption = ("🎧 Here's your MP3!"
                   if entry.get("kind") == "audio" else COPY_CAPTION)
        return {"chat_id": chat_id,
                "from_chat_id": _worker_channel_id(),
                "message_id": mid,
                "caption": caption}
    except Exception:
        return None


def note_done(job_id):
    """Mark a job delivered. Returns True when it was pending. Never raises."""
    try:
        jobs = _load_jobs()
        entry = jobs.get(job_id)
        if isinstance(entry, dict) and entry.get("status") == "pending":
            entry["status"] = "done"
            entry["done_ts"] = time.time()
            _job_update(job_id, entry)
            logger.info("[WORKER][DELIVERED] job %s (signal from channel)",
                        job_id)
            return True
        return False
    except Exception:
        return False


def note_failed(job_id):
    """Mark a job failed. Returns the entry (for local fallback) or None."""
    try:
        jobs = _load_jobs()
        entry = jobs.get(job_id)
        if isinstance(entry, dict) and entry.get("status") == "pending":
            entry["status"] = "failed"
            _job_update(job_id, entry)
            return entry
        return None
    except Exception:
        return None


def pending_expired(now=None):
    """Pending jobs older than the timeout — ready for local fallback."""
    try:
        now = time.time() if now is None else now
        return [e for e in _load_jobs().values()
                if isinstance(e, dict)
                and e.get("status") == "pending"
                and now - e.get("ts", 0) > _WORKER_TIMEOUT_SECS]
    except Exception:
        return []


def mark_expired(job_id):
    """Flag a job as expired so it isn't picked up twice. Never raises."""
    try:
        jobs = _load_jobs()
        entry = jobs.get(job_id)
        if isinstance(entry, dict) and entry.get("status") == "pending":
            entry["status"] = "expired"
            _job_update(job_id, entry)
    except Exception:
        pass


def pending_count():
    """How many jobs are still waiting on the worker (for logs/health)."""
    try:
        return sum(1 for e in _load_jobs().values()
                   if isinstance(e, dict) and e.get("status") == "pending")
    except Exception:
        return 0
