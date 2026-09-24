import logging
from typing import Optional, Dict, Tuple
import os
import re
import time
import yt_dlp
import unicodedata
import string
import glob as globmod
import requests

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in filename if c in valid_chars)
    filename = filename.replace(' ', '_')
    return filename or 'video'

def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/)([^&?/]+)',
        r'youtube.com/shorts/([^&?/]+)'
    ]
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    return None

def validate_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


# Round 16: quality adapts to Telegram's 50MB cap instead of a hard 720p
# ceiling. yt-dlp picks the BEST quality whose streams fit under ~45MB —
# short videos get 1080p when it fits, long ones drop to whatever fits.
# The 50MB post-download check in download_youtube_video stays as a
# safety net for the rare unrestricted-fallback case.
_DOWNLOAD_FORMAT = (
    'bestvideo[filesize<40M]+bestaudio[filesize<5M]/'
    'best[filesize<45M]/'
    'bestvideo+bestaudio/best'
)


def _pick_downloaded_file(video_id: str) -> Optional[str]:
    """Return the finished download for a video id, or None.

    Round 16: picks the largest non-temp match instead of matches[0], so a
    leftover file from an earlier failed run can't shadow the new download.
    """
    matches = globmod.glob(os.path.join(os.getcwd(), f'youtube_{video_id}.*'))
    matches = [m for m in matches
               if not m.endswith(('.part', '.ytdl', '.temp', '.tmp'))
               and os.path.isfile(m)]
    if not matches:
        return None
    return max(matches, key=os.path.getsize)

# Permanent-failure hints for the video path: another player client will not
# fix these, so the client rotation stops immediately.  NOTE: the bot-check
# ("sign in to confirm you're not a bot") is deliberately NOT here — it
# flaps per client and is the whole reason the rotation exists.
_VIDEO_PERMANENT_HINTS = (
    'private video', 'private', 'age-restricted', 'age restricted',
    'confirm your age', 'requires authentication', 'copyright', 'drm',
    'not available', 'unavailable',
)


def _is_permanent_video_error(error_msg: str) -> bool:
    # A format refused by one client is often served by another, so the
    # format-specific phrasing rotates; a video that is itself gone does not.
    if 'requested format' in error_msg or 'format not available' in error_msg:
        return False
    return any(h in error_msg for h in _VIDEO_PERMANENT_HINTS)


def _download_video_with_client(url: str, video_id: str,
                                output_template: str,
                                client: str) -> Tuple[bool, object]:
    """One /download attempt through a single YouTube player client.

    Returns (True, (file_path, success_msg)) on success, or (False, notice)
    on genuine failures (too long / file missing / too large).  Raises
    yt_dlp.utils.DownloadError for everything else so the caller can rotate
    to the next client.
    """
    ydl_opts = {
        'format': _DOWNLOAD_FORMAT,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'outtmpl': output_template,
        'restrictfilenames': True,
        'socket_timeout': 30,
        'retries': 3,
        'extractor_args': {'youtube': {'player_client': [client]}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get('duration', 0) or 0

        if duration > 600:
            return False, (
                "😕 Video Too Long\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Max duration: 10 minutes.\n"
                "This video is {0}:{1:02d}.\n"
                "Try a shorter video.".format(duration // 60, duration % 60)
            )

        ydl.download([url])

        file_path = _pick_downloaded_file(video_id)
        if not file_path:
            logger.error(f"No downloaded file found for video_id: {video_id}")
            return False, (
                "😕 Download Failed\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "The file couldn't be saved.\n"
                "Try a different video."
            )

        file_size = os.path.getsize(file_path)
        file_size_mb = round(file_size / (1024 * 1024), 1)

        if file_size > 50 * 1024 * 1024:
            cleanup_video(file_path)
            return False, (
                "😕 File Too Large\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Downloaded file is {file_size_mb}MB.\n"
                "Telegram limit is 50MB.\n"
                "Try a shorter video."
            )

        views = info.get('view_count', 0) or 0
        success_msg = (
            f"✅ Downloaded!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📽️ {info.get('title', 'Video')}\n"
            f"👤 {info.get('uploader', 'Unknown')}\n"
            f"⏱️ {duration//60}:{duration%60:02d}  •  📦 {file_size_mb}MB\n"
        )
        if views:
            success_msg += f"👀 {views:,} views\n"
        success_msg += "\n🚀 Uploading to Telegram..."

        return True, (file_path, success_msg)


def download_youtube_video(url: str) -> Tuple[bool, str]:
    global _LAST_DOWNLOAD_WAVE
    _LAST_DOWNLOAD_WAVE = False
    try:
        logger.info(f"Starting download process for URL: {url}")

        if not validate_youtube_url(url):
            return False, (
                "😕 Invalid YouTube URL\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please provide a valid YouTube link:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/..."
            )

        video_id = extract_video_id(url)
        output_template = f'youtube_{video_id}.%(ext)s'

        # Round 30: rotate YouTube player clients (android -> web -> ios),
        # one client per attempt.  YouTube's bot-check ("sign in to confirm
        # you're not a bot") flaps per client — the web player can be
        # challenged while android/ios sail through on the same IP, and a
        # format refused by one client is often served by another.  (The
        # MP3 path already rotates the same tuple.)  Permanent failures
        # stop the rotation at once; the shared breaker only trips when
        # EVERY client hits a hard block error, so one challenged client no
        # longer queues the request.
        last_err: Optional[BaseException] = None
        block_hits = 0
        for client in _YT_CLIENT_ATTEMPTS:
            try:
                return _download_video_with_client(
                    url, video_id, output_template, client)
            except yt_dlp.utils.DownloadError as e:
                last_err = e
                error_msg = str(e).lower()
                logger.error(f"yt-dlp DownloadError (client={client}): {e}")
                if _is_permanent_video_error(error_msg):
                    break
                if _is_block_error(e):
                    block_hits += 1
                    logger.warning(f"[VIDEO] client={client} blocked by "
                                   f"YouTube, trying next client")

        # Every client failed (or a permanent error stopped the rotation).
        # A /download that hits a hard YouTube block on ALL clients is
        # itself proof of a wave — register it on the shared breaker so
        # download_command queues this request for auto-retry (instead of
        # showing a failure) and the MP3 path also treats YouTube as
        # blocked.  Genuine failures (private, age-restricted,
        # unavailable...) leave the breaker alone.
        if block_hits >= len(_YT_CLIENT_ATTEMPTS):
            _yt_trip_breaker("download: all player clients blocked")
            _LAST_DOWNLOAD_WAVE = True

        error_msg = str(last_err).lower() if last_err else ""
        if "private video" in error_msg or "private" in error_msg:
            reason = "This video is private."
        elif "not a bot" in error_msg:
            reason = ("YouTube is temporarily blocking automated downloads "
                      "(bot check). Try again in a few minutes.")
        elif ("age restricted" in error_msg or "age-restricted" in error_msg
                or "confirm your age" in error_msg):
            reason = "This video is age-restricted."
        elif "copyright" in error_msg:
            reason = "Blocked due to copyright."
        elif "not available" in error_msg or "unavailable" in error_msg:
            reason = "Video is not available (may be region-locked or deleted)."
        elif "sign in" in error_msg or "login" in error_msg:
            reason = "Requires authentication to access."
        elif "429" in error_msg or "too many" in error_msg:
            reason = "YouTube rate limit. Wait a few minutes."
        elif "requested format" in error_msg:
            reason = "No compatible format available. This is a YouTube restriction."
        else:
            reason = "YouTube blocked the download."

        return False, (
            f"😕 Download Failed\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Reason: {reason}\n\n"
            f"💡 Tips:\n"
            f"• Try a different video\n"
            f"• Shorter/older videos work better\n"
            f"• Unofficial uploads are easier to download"
        )

    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        return False, (
            "😕 Download Failed\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "An unexpected error occurred.\n\n"
            "💡 Tips:\n"
            "• Check the URL is correct\n"
            "• Try a different video\n"
            "• Wait a minute and retry"
        )


# ── MP3 v2 ────────────────────────────────────────────────────────────────
# Rebuilt 2026-09-24: the old engine downloaded candidates in search order
# and kept the first one big enough — remixes often won. The new engine:
#   1. Scores every candidate by TITLE match + uploader + DURATION before
#      downloading anything (remix/cover/sped-up markers are penalized,
#      duration far from the lrclib original is rejected).
#   2. Downloads only the top 1–2 scored candidates instead of trying up to
#      20 in order (much faster).
#   3. Caches: Telegram file_id cache (repeat requests are instant — no
#      download, no upload) + disk cache of the MP3 itself.
import hashlib as _hashlib
import json as _json
import time as _time

_MP3_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP3_CACHE_DIR = os.path.join(_MP3_BASE_DIR, 'mp3_cache')
_MP3_FILEID_JSON = os.path.join(MP3_CACHE_DIR, 'file_ids.json')
_MP3_MAX_FILES = 300          # LRU cap on cached MP3s
_MP3_MAX_BYTES = 1500 * 1024 * 1024

_MIN_SONG_BYTES = 800_000     # < 800 KB = likely a short preview, skip it
_MIN_SONG_SECS  = 90          # < 90 s duration in metadata = likely a preview

# ── Resilience: YouTube circuit breaker + failure/URL memory ─────────────
# YouTube bot-blocks this server's IP in waves (search dies with
# IncompleteRead / "sign in to confirm you're not a bot", then recovers
# on its own). Hammering it during a wave only burns a minute per tap.
# The breaker skips YouTube entirely while a wave is active.
_YT_BREAKER_SECS = 900        # 15 min — waves usually pass within this
_YT_BLOCKED_UNTIL = 0.0
_BLOCK_ERROR_HINTS = (
    'not a bot', 'sign in to confirm', 'incompleteread',
    'unable to download api page', 'http error 403', 'http error 429',
    'too many requests',
)
# Soft-wave hints: stalls and per-video format refusals that arrive
# back-to-back across DIFFERENT candidates. One of these is bad luck;
# two in a row is YouTube throttling this server (a wave). The breaker
# only trips on hard block errors today, so a half-working YouTube can
# burn 45s x N candidates (~5 min) on doomed attempts before failing.
_SOFT_WAVE_HINTS = (
    'timed out', 'timeout', 'stalled',
    'requested format is not available', 'format not available',
    'read operation timed out', 'giving up after',
)
_WAVE_ABORT_STRIKES = 2  # consecutive soft failures -> wave: fail fast
_MP3_FAILURES_JSON = os.path.join(MP3_CACHE_DIR, 'mp3_failures.json')
_MP3_URLS_JSON = os.path.join(MP3_CACHE_DIR, 'mp3_urls.json')
_FAILURE_TTL_SECS = 600       # 10 min — a repeat tap fails instantly
_CANDIDATE_TIMEOUT_SECS = 45  # hard cap per download attempt


def _is_block_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(h in msg for h in _BLOCK_ERROR_HINTS)


def _is_soft_wave_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(h in msg for h in _SOFT_WAVE_HINTS)


def _yt_breaker_open() -> bool:
    return _time.time() < _YT_BLOCKED_UNTIL


# Whether the most recent download_youtube_video() call failed because of a
# YouTube block wave (as opposed to a genuine failure like a private video
# or a bad URL). Lets callers queue ONLY wave-caused failures for auto-retry:
# gating on "breaker is open" alone also queues garbage that failed for
# unrelated reasons mid-wave.
_LAST_DOWNLOAD_WAVE = False


def download_hit_block_wave() -> bool:
    """True if the latest download_youtube_video() call failed on a YouTube
    block wave. Never raises."""
    return _LAST_DOWNLOAD_WAVE


def _yt_trip_breaker(reason: str) -> None:
    global _YT_BLOCKED_UNTIL
    _YT_BLOCKED_UNTIL = _time.time() + _YT_BREAKER_SECS
    logger.warning(f"[MP3][BREAKER] YouTube blocked for {_YT_BREAKER_SECS // 60}min: {reason}")


def _failure_get(key: str):
    """Recent total-failure memory: (message, age_secs) or None."""
    try:
        with open(_MP3_FAILURES_JSON, 'r', encoding='utf-8') as f:
            entry = _json.load(f).get(key)
        if entry and (_time.time() - entry.get('ts', 0)) < _FAILURE_TTL_SECS:
            return entry.get('msg'), _time.time() - entry.get('ts', 0)
    except Exception:
        pass
    return None


def _failure_note(key: str, msg: str) -> None:
    try:
        from utils import locked_json_update
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)

        def _update(data):
            data[key] = {'ts': _time.time(), 'msg': msg}
            # keep the file small — drop entries older than the TTL
            cutoff = _time.time() - _FAILURE_TTL_SECS
            for k in [k for k, v in data.items()
                      if _time.time() - v.get('ts', 0) > cutoff]:
                data.pop(k, None)
            return data

        locked_json_update(_MP3_FAILURES_JSON, _update)
    except Exception:
        pass


def _winurl_get(key: str) -> Optional[str]:
    try:
        with open(_MP3_URLS_JSON, 'r', encoding='utf-8') as f:
            return _json.load(f).get(key)
    except Exception:
        return None


def _winurl_note(key: str, url: str) -> None:
    """Remember which URL actually downloaded, for block-wave retries."""
    try:
        from utils import locked_json_update
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)

        def _update(data):
            data[key] = url
            # cap size — oldest inserts evicted first (dict order)
            while len(data) > 500:
                data.pop(next(iter(data)))
            return data

        locked_json_update(_MP3_URLS_JSON, _update)
    except Exception:
        pass


# ── MP3 retry queue (block-wave auto-retry) ────────────────────────────────
# When a download fails during a YouTube block wave, the request is queued
# instead of dead-ending.  A scheduler tick (every 5 min) retries each
# queued song once the breaker has cleared, and the MP3 is delivered
# automatically — the user never has to tap again.
_MP3_RETRY_JSON = os.path.join(MP3_CACHE_DIR, 'mp3_retry_queue.json')
_RETRY_TTL_SECS = 3 * 3600   # give up on a queued request after 3h
_RETRY_MAX_ATTEMPTS = 3      # initial try + up to 2 queued retries


def mp3_block_wave_active() -> bool:
    """Public: is YouTube currently in a block wave (breaker open)?"""
    return _yt_breaker_open()


def mp3_forget_failure(artist: str, song: str) -> None:
    """Clear the recent-failure memory so a queued retry runs a real attempt."""
    try:
        from utils import locked_json_update
        key = _mp3_cache_key(artist, song)

        def _update(data):
            data.pop(key, None)
            return data

        locked_json_update(_MP3_FAILURES_JSON, _update)
    except Exception:
        pass


def mp3_retry_enqueue(chat_id: int, user_id: int,
                      artist: str, song: str) -> bool:
    """Queue a block-wave-failed request for automatic retry. Never raises."""
    try:
        from utils import locked_json_update
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)
        key = _mp3_cache_key(artist, song)

        def _update(data):
            data[key] = {'chat_id': chat_id, 'user_id': user_id,
                         'artist': artist, 'song': song,
                         'ts': _time.time(), 'attempts': 0}
            # keep the queue small — drop expired entries on insert
            now = _time.time()
            for k in [k for k, v in data.items()
                      if now - v.get('ts', 0) > _RETRY_TTL_SECS]:
                data.pop(k, None)
            return data

        locked_json_update(_MP3_RETRY_JSON, _update)
        logger.info(f"[MP3][RETRY] queued '{artist} - {song}' for user {user_id}")
        return True
    except Exception:
        return False


def mp3_retry_due() -> list:
    """Queued entries ready for a retry: breaker closed, not expired."""
    try:
        if _yt_breaker_open():
            return []
        with open(_MP3_RETRY_JSON, 'r', encoding='utf-8') as f:
            data = _json.load(f)
    except Exception:
        return []
    now = _time.time()
    out = []
    for key, e in data.items():
        if not isinstance(e, dict):
            continue
        if now - e.get('ts', 0) > _RETRY_TTL_SECS:
            continue
        if e.get('attempts', 0) >= _RETRY_MAX_ATTEMPTS:
            continue
        entry = dict(e)
        entry['key'] = key
        out.append(entry)
    return out


def mp3_retry_note_attempt(key: str) -> None:
    """Increment the attempt counter for a queued entry. Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            if key in data:
                data[key]['attempts'] = data[key].get('attempts', 0) + 1
            return data

        locked_json_update(_MP3_RETRY_JSON, _update)
    except Exception:
        pass


def mp3_retry_remove(key: str) -> None:
    """Drop a queued entry (delivered or given up). Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            data.pop(key, None)
            return data

        locked_json_update(_MP3_RETRY_JSON, _update)
    except Exception:
        pass


# Round 17: /download gets the same no-re-tap treatment as /mp3. Video has
# no alternative source (YouTube is the only video provider, unlike MP3's
# three audio sources), so a block wave can't be routed around — but the
# request can be queued and auto-delivered once the wave clears. Shares the
# same breaker, TTL and attempt budget as the MP3 queue.
_VIDEO_RETRY_JSON = os.path.join(MP3_CACHE_DIR, 'video_retry_queue.json')


def _video_retry_key(user_id: int, video_id: str) -> str:
    return f"{user_id}:{video_id}"


def video_retry_enqueue(chat_id: int, user_id: int, url: str) -> bool:
    """Queue a block-wave-failed /download for automatic retry. Never raises."""
    try:
        from utils import locked_json_update
        video_id = extract_video_id(url) or url
        key = _video_retry_key(user_id, video_id)
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)

        def _update(data):
            data[key] = {'chat_id': chat_id, 'user_id': user_id,
                         'url': url, 'video_id': video_id,
                         'ts': _time.time(), 'attempts': 0}
            # keep the queue small — drop expired entries on insert
            now = _time.time()
            for k in [k for k, v in data.items()
                      if now - v.get('ts', 0) > _RETRY_TTL_SECS]:
                data.pop(k, None)
            return data

        locked_json_update(_VIDEO_RETRY_JSON, _update)
        logger.info(f"[VIDEO][RETRY] queued '{video_id}' for user {user_id}")
        return True
    except Exception:
        return False


def video_retry_due() -> list:
    """Queued video entries ready for a retry: breaker closed, not expired."""
    try:
        if _yt_breaker_open():
            return []
        with open(_VIDEO_RETRY_JSON, 'r', encoding='utf-8') as f:
            data = _json.load(f)
    except Exception:
        return []
    now = _time.time()
    out = []
    for key, e in data.items():
        if not isinstance(e, dict):
            continue
        if now - e.get('ts', 0) > _RETRY_TTL_SECS:
            continue
        if e.get('attempts', 0) >= _RETRY_MAX_ATTEMPTS:
            continue
        entry = dict(e)
        entry['key'] = key
        out.append(entry)
    return out


def video_retry_note_attempt(key: str) -> None:
    """Increment the attempt counter for a queued video entry. Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            if key in data:
                data[key]['attempts'] = data[key].get('attempts', 0) + 1
            return data

        locked_json_update(_VIDEO_RETRY_JSON, _update)
    except Exception:
        pass


def video_retry_remove(key: str) -> None:
    """Drop a queued video entry (delivered or given up). Never raises."""
    try:
        from utils import locked_json_update

        def _update(data):
            data.pop(key, None)
            return data

        locked_json_update(_VIDEO_RETRY_JSON, _update)
    except Exception:
        pass

# Title markers that (almost) always mean "not the original". Penalized
# unless the requested song title itself contains the marker.
_REMIX_MARKERS = (
    'remix', 'cover', 'sped up', 'spedup', 'slowed', 'nightcore', 'mashup',
    'unplugged', 'acoustic', '8d', 'flip', 'bootleg', 'extended',
    'karaoke', 'instrumental', 'reverb', 'tiktok',
    # Reaction videos ("Twins React to X ...") — talking over the music,
    # never a valid audio source. Phrased (not bare 'react') so a song
    # genuinely titled "React" is untouched.
    'reaction', 'react to', 'reacts to',
)


def _norm_key_text(t: str) -> str:
    t = unicodedata.normalize('NFKD', t or '').encode('ASCII', 'ignore').decode()
    return re.sub(r'\s+', ' ', t.lower().strip())


def _mp3_cache_key(artist: str, song: str) -> str:
    return _hashlib.md5(
        f"{_norm_key_text(artist)}|{_norm_key_text(song)}".encode()
    ).hexdigest()


def _norm_title(t: str) -> str:
    """Normalize a track title for relevance scoring."""
    t = _norm_key_text(t)
    t = re.sub(r'[\(\[]\s*(feat|ft|with)\.?[^\)\]]*[\)\]]', '', t)
    t = re.sub(r'\s*[-–—]\s*(feat|ft)\.?\s.*$', '', t)
    t = re.sub(r'[\(\)\[\]_\-–—.,!?\"\'’“”]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


# ── Expected duration (lrclib) ─────────────────────────────────────────────
_dur_cache: Dict[str, Optional[int]] = {}


def _expected_duration(artist: str, song: str) -> Optional[int]:
    """Original-track duration in seconds from lrclib (fast, cached)."""
    key = _mp3_cache_key(artist, song)
    if key in _dur_cache:
        return _dur_cache[key]
    dur = None
    try:
        r = requests.get(
            'https://lrclib.net/api/get',
            params={'artist_name': artist, 'track_name': song},
            timeout=4,
            headers={'User-Agent': 'LyricsMasterBot/1.0'},
        )
        if r.status_code == 200:
            d = r.json().get('duration')
            if d:
                dur = int(float(d))
                logger.info(f"[MP3][DUR] lrclib: '{artist} - {song}' → {dur}s")
    except Exception as e:
        logger.debug(f"[MP3][DUR] lrclib lookup failed: {type(e).__name__}")
    _dur_cache[key] = dur
    return dur


# ── Candidate scoring ──────────────────────────────────────────────────────
def _score_candidate(title: str, uploader: str, duration: int,
                     artist: str, song: str,
                     expected_dur: Optional[int]) -> float:
    """Relevance score for a download candidate. Higher = better.

    Returns a very negative number for near-certain wrong tracks
    (remix-length durations, previews).
    """
    t = _norm_title(title)
    s = _norm_title(song) or _norm_title(artist)  # artist-only MP3: match artist tokens
    a = _norm_title(artist)
    u = _norm_title(uploader or '')
    if not s:
        return -1e9

    score = 0.0

    # 1. Song-title token overlap (the most important signal)
    st, tt = s.split(), t.split()
    if st:
        overlap = len(set(st) & set(tt)) / len(set(st))
        score += overlap * 50
        if s == t or s in t:
            score += 25

    # 2. Artist name in title or uploader
    at = a.split()
    if at:
        in_title = len(set(at) & set(tt)) / len(at)
        in_upl = len(set(at) & set(u.split())) / len(at)
        score += max(in_title, in_upl) * 25
        if a and (a in u or u in a):
            score += 15  # official channel bonus

    # 3. Remix-marker penalty (unless the song itself has the marker)
    song_markers = {m for m in _REMIX_MARKERS if m in s}
    for m in _REMIX_MARKERS:
        if m in t and m not in song_markers:
            score -= 60
            break

    # 3b. Mystery-credit penalty: "(CH4YN)", "[BENDA FLIP]", "ft. Nicki Minaj"
    # when the query names no such credit almost always means a fan
    # remix/edit. Official tags like (Official Audio) are exempt.
    _OFFICIAL_TAGS = ('official', 'lyric', 'visualiz', 'music video')
    raw_parens = re.findall(r'[\(\[](.*?)[\)\]]', title or '')
    for p in raw_parens:
        if any(k in p.lower() for k in _OFFICIAL_TAGS):
            continue
        pn = _norm_title(p)
        if pn and pn not in s and not set(pn.split()) <= (set(st) | set(at)):
            score -= 40
            break
    mfeat = re.search(r'\b(?:ft|feat)\.?\s+([a-z0-9][a-z0-9 .&]*)', t)
    if mfeat:
        feat = mfeat.group(1).strip()
        if (feat and feat not in s and feat not in a
                and not (set(feat.split()) & (set(st) | set(at)))):
            score -= 40

    # 4. Duration sanity vs the original recording
    dur = int(duration or 0)
    if expected_dur and dur:
        ratio = dur / expected_dur
        if ratio < 0.55 or ratio > 1.8:
            # Far too short (preview) or far too long (extended/remix/mix)
            return -1e9
        score += 20 * max(0.0, 1 - abs(1 - ratio) * 2)
    elif dur and dur < _MIN_SONG_SECS:
        return -1e9

    return score


# ── SoundCloud search ──────────────────────────────────────────────────────
def _sc_search_entries(query: str, n: int = 8) -> list:
    """Flat SoundCloud search; returns entry dicts with title/uploader/duration/url."""
    logger.info(f"[MP3][SEARCH] SoundCloud scsearch{n}: '{query}'")
    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True,
            'socket_timeout': 12}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(f'scsearch{n}:{query}', download=False)
    except Exception as e:
        logger.warning(f"[MP3][SEARCH] SoundCloud error: {type(e).__name__}: {e}")
        return []
    entries = []
    if isinstance(meta, dict):
        entries = meta.get('entries', []) or []
        if not entries and meta.get('id'):
            entries = [meta]
    out = [e for e in entries if e.get('webpage_url') or e.get('url')]
    logger.info(f"[MP3][SEARCH] '{query}' → {len(out)} usable result(s)")
    return out


# ── YouTube search ─────────────────────────────────────────────────────────
def _yt_search_entries(query: str, n: int = 5) -> list:
    """Flat YouTube search; returns entry dicts with title/duration/url."""
    logger.info(f"[MP3][SEARCH] YouTube ytsearch{n}: '{query}'")
    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True,
            'socket_timeout': 15}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(f'ytsearch{n}:{query}', download=False)
    except Exception as e:
        logger.warning(f"[MP3][SEARCH] YouTube error: {type(e).__name__}: {e}")
        if _is_block_error(e):
            _yt_trip_breaker(f"search '{query}': {type(e).__name__}")
        return []
    entries = []
    if isinstance(meta, dict):
        entries = meta.get('entries', []) or []
    out = [e for e in entries if e.get('url')]
    logger.info(f"[MP3][SEARCH] '{query}' → {len(out)} usable result(s)")
    return out


# ── Audius search ──────────────────────────────────────────────────────────
# Third audio provider, independent of YouTube/SoundCloud: the free Audius
# API (discoveryprovider.audius.co).  Catalog skews indie, but during a
# YouTube block wave it is often the difference between success and
# "not available".  Stream URLs return audio/mpeg directly.
_AUDIUS_APP = "lyricsmasterbot"
_AUDIUS_BASE = "https://discoveryprovider.audius.co/v1"


def _audius_search_entries(query: str, n: int = 8) -> list:
    """Flat Audius search; returns entry dicts with title/uploader/duration/url."""
    logger.info(f"[MP3][SEARCH] Audius: '{query}'")
    try:
        r = requests.get(
            f"{_AUDIUS_BASE}/tracks/search",
            params={"query": query, "app_name": _AUDIUS_APP, "limit": n},
            timeout=12,
            headers={"User-Agent": "LyricsMasterBot/1.0"})
        data = r.json().get("data") or []
    except Exception as e:
        logger.warning(f"[MP3][SEARCH] Audius error: {type(e).__name__}: {e}")
        return []
    out = []
    for t in data:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        title = (t.get("title") or "").strip()
        if not tid or not title:
            continue
        out.append({
            "title": title,
            "uploader": str((t.get("user") or {}).get("name") or ""),
            "duration": int(t.get("duration") or 0),
            "webpage_url": (f"{_AUDIUS_BASE}/tracks/{tid}/stream"
                            f"?app_name={_AUDIUS_APP}"),
        })
    logger.info(f"[MP3][SEARCH] '{query}' → {len(out)} usable result(s)")
    return out


# ── Cache helpers ──────────────────────────────────────────────────────────
def _fileid_get(key: str) -> Optional[str]:
    try:
        with open(_MP3_FILEID_JSON, 'r', encoding='utf-8') as f:
            return _json.load(f).get(key)
    except Exception:
        return None


def note_mp3_file_id(artist: str, song: str, file_id: str) -> None:
    """Persist a Telegram file_id so the next request for this song is instant."""
    try:
        from utils import locked_json_update
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)

        def _update(data):
            data[_mp3_cache_key(artist, song)] = file_id
            return data

        locked_json_update(_MP3_FILEID_JSON, _update)
        logger.info(f"[MP3][CACHE] file_id stored for '{artist} - {song}'")
    except Exception as e:
        logger.debug(f"[MP3][CACHE] file_id store failed: {type(e).__name__}")


def forget_mp3_file_id(artist: str, song: str) -> None:
    """Drop a stale Telegram file_id so the next request re-downloads fresh."""
    try:
        from utils import locked_json_update

        def _update(data):
            data.pop(_mp3_cache_key(artist, song), None)
            return data

        locked_json_update(_MP3_FILEID_JSON, _update)
        logger.info(f"[MP3][CACHE] stale file_id dropped for '{artist} - {song}'")
    except Exception as e:
        logger.debug(f"[MP3][CACHE] file_id drop failed: {type(e).__name__}")


def _disk_cache_path(key: str) -> str:
    return os.path.join(MP3_CACHE_DIR, f"{key}.mp3")


def _disk_cache_get(key: str) -> Optional[str]:
    p = _disk_cache_path(key)
    if os.path.exists(p) and os.path.getsize(p) >= _MIN_SONG_BYTES:
        return p
    return None


def _disk_cache_put(key: str, src_path: str) -> Optional[str]:
    """Move a fresh download into the cache dir (LRU-evicted). Returns cache path."""
    try:
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)
        dest = _disk_cache_path(key)
        if os.path.abspath(src_path) != os.path.abspath(dest):
            if os.path.exists(dest):
                os.remove(dest)
            os.rename(src_path, dest)
        _evict_cache_if_needed()
        return dest
    except Exception as e:
        logger.warning(f"[MP3][CACHE] store failed: {type(e).__name__}: {e}")
        return src_path if os.path.exists(src_path) else None


def _evict_cache_if_needed() -> None:
    try:
        files = [os.path.join(MP3_CACHE_DIR, f) for f in os.listdir(MP3_CACHE_DIR)
                 if f.endswith('.mp3')]
        total = sum(os.path.getsize(f) for f in files)
        if len(files) <= _MP3_MAX_FILES and total <= _MP3_MAX_BYTES:
            return
        files.sort(key=lambda f: os.path.getmtime(f))  # oldest first
        while (len(files) > _MP3_MAX_FILES or total > _MP3_MAX_BYTES) and files:
            f = files.pop(0)
            try:
                total -= os.path.getsize(f)
                os.remove(f)
            except OSError:
                pass
        logger.info("[MP3][CACHE] evicted oldest entries")
    except Exception as e:
        logger.debug(f"[MP3][CACHE] eviction failed: {type(e).__name__}")


def is_cached_mp3_path(path: str) -> bool:
    """True when path lives inside the MP3 cache (handler must NOT delete it)."""
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(MP3_CACHE_DIR)]
        ) == os.path.abspath(MP3_CACHE_DIR)
    except Exception:
        return False


# ── Download helper (unchanged semantics) ──────────────────────────────────
# One client per attempt: yt-dlp merges formats across every requested
# client, so a mixed list can pick a web-client format URL that then 403s.
# Rotating single clients keeps the chosen format on the client that
# produced it. Permanent failures (DRM, private, age-gated, copyright,
# deleted) abort the rotation immediately.
_YT_CLIENT_ATTEMPTS = ('android', 'web', 'ios')
# Permanent failures abort the client rotation immediately. NOTE: YouTube's
# bot-check ("sign in to confirm you're not a bot") is TRANSIENT — it flaps
# per client — so only the age-gate phrasing ("confirm your age") is listed.
_PERMANENT_DL_ERRORS = ('drm', 'private video', 'age-restricted',
                        'age restricted', 'copyright', 'unavailable',
                        'not available', 'requires authentication',
                        'sign in to confirm your age')


def _download_url_to_mp3(download_url: str, file_prefix: str, label: str) -> str:
    """
    Download bestaudio from a resolved URL and convert to a real MP3
    (192k) with ffmpeg. Returns the .mp3 path.
    """
    logger.info(f"[MP3][DOWNLOAD] Starting | provider={label} | url='{download_url}'")
    output_template = f'{file_prefix}.%(ext)s'
    is_youtube = 'youtube.com' in download_url or 'youtu.be' in download_url
    clients = _YT_CLIENT_ATTEMPTS if is_youtube else (None,)
    last_err: Optional[Exception] = None

    def _clean_partials():
        for m in globmod.glob(os.path.join(os.getcwd(), f'{file_prefix}.*')):
            try:
                os.remove(m)
            except OSError:
                pass

    for client in clients:
        _clean_partials()
        dl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'socket_timeout': 20,
            'retries': 2,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        if client:
            dl_opts['extractor_args'] = {'youtube': {'player_client': [client]}}
        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                ret = ydl.download([download_url])
            if ret != 0:
                raise RuntimeError(f"yt-dlp returned non-zero code: {ret}")
            last_err = None
            break
        except yt_dlp.utils.DownloadError as de:
            last_err = de
            logger.warning(f"[MP3][DOWNLOAD] DownloadError | provider={label} "
                           f"| client={client}: {de}")
            if any(k in str(de).lower() for k in _PERMANENT_DL_ERRORS):
                _clean_partials()
                raise
        except Exception as e:
            last_err = e
            logger.warning(f"[MP3][DOWNLOAD] Error | provider={label} "
                           f"| client={client}: {type(e).__name__}: {e}")
        time.sleep(2)

    if last_err is not None:
        # Final attempt failed: clean its partials too (the loop only cleans
        # at the START of each attempt, leaking the last attempt's .part).
        _clean_partials()
        raise last_err

    mp3_path = os.path.join(os.getcwd(), f'{file_prefix}.mp3')
    if os.path.exists(mp3_path):
        audio_path = mp3_path
    else:
        # ffmpeg conversion failed — fall back to whatever audio we got
        matches = [m for m in globmod.glob(os.path.join(os.getcwd(), f'{file_prefix}.*'))
                   if not m.endswith('.part')]
        if not matches:
            logger.warning(f"[MP3][FILE] No file found after download | provider={label}")
            raise FileNotFoundError(f"audio file not found after download via {label}")
        audio_path = matches[0]
        logger.info(f"[MP3][FILE] ffmpeg skipped, raw audio: '{audio_path}'")

    size_bytes = os.path.getsize(audio_path)
    logger.info(f"[MP3][FILE] OK | provider={label} | path='{audio_path}' "
                f"| size={round(size_bytes/1024/1024, 2)}MB")
    return audio_path



def _clean_song_title(title: str) -> str:
    """Strip features/parentheticals for simpler searches."""
    title = re.sub(r'\s*[\(\[](feat|ft|with|prod|remix)[^\)\]]*[\)\]]', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*-\s*(feat|ft)\.?\s+.+$', '', title, flags=re.IGNORECASE)
    return title.strip()


def _clean_artist_hint(artist: str) -> str:
    """Strip 'feat. ...' from artist name so 'Rihanna feat. JAY-Z' matches 'Rihanna'."""
    return re.sub(r'\s*(feat\.|ft\.|featuring).*$', '', artist, flags=re.IGNORECASE).strip()


def _build_success_msg(title: str, uploader: str, duration: int, file_size_mb: float) -> str:
    dur_str = f"{duration//60}:{duration%60:02d}" if duration else "?"
    return (
        f"🎵 MP3 Ready!\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎤 {title}\n"
        f"👤 {uploader}\n"
        f"⏱️ {dur_str}  •  📦 {file_size_mb}MB\n\n"
        f"🚀 Uploading..."
    )


# ── Main entry point ───────────────────────────────────────────────────────
def download_audio_for_song(artist: str, song: str,
                            on_stage=None) -> Tuple[bool, any]:
    """
    Download MP3 for a song. Returns (True, result) where result is either:
      ('file_id', telegram_file_id, title, uploader) — instant, cached on Telegram
      (file_path, info_message, title, uploader)     — fresh or disk-cached file
    or (False, error_message).

    on_stage(text) is called with short progress updates for the UI.
    """
    def stage(msg: str):
        if on_stage:
            try:
                on_stage(msg)
            except Exception:
                pass

    artist = (artist or '').strip()
    song = (song or '').strip()
    query = f"{artist} - {song}" if song else artist
    key = _mp3_cache_key(artist, song)
    os.makedirs(MP3_CACHE_DIR, exist_ok=True)
    logger.info(f"[MP3][START] artist='{artist}' | song='{song}'")

    # ── Tier 0: Telegram file_id cache — instant, no download, no upload ──
    fid = _fileid_get(key)
    if fid:
        logger.info(f"[MP3][HIT] file_id cache for '{query}'")
        return True, ('file_id', fid, query, artist)

    # ── Tier 1: disk cache ────────────────────────────────────────────────
    cached = _disk_cache_get(key)
    if cached:
        size_mb = round(os.path.getsize(cached) / 1024 / 1024, 1)
        logger.info(f"[MP3][HIT] disk cache for '{query}' ({size_mb}MB)")
        return True, (cached,
                      _build_success_msg(query, artist, 0, size_mb) + "\n⚡ Served from cache",
                      query, artist)

    # ── Tier 1.5: recent-failure memory — a repeat tap fails instantly ────
    # instead of burning another minute on a hopeless song.
    recent_fail = _failure_get(key)
    if recent_fail:
        msg, age = recent_fail
        logger.info(f"[MP3][HIT] failure memory for '{query}' ({age:.0f}s old)")
        return False, msg + "\n\n(Last tried moments ago — retry in a few minutes.)"

    # ── Tier 2: fresh resolve (providers run in parallel) ──────────────────
    # SoundCloud + YouTube + Audius searches and the lrclib duration lookup
    # are independent — run them together, then score ALL candidates globally
    # and download only the best. Audiomack's API is dead (returns HTML),
    # so it was dropped.
    stage("🔍 Finding the original track…")

    def _sc_all():
        # One query is enough — SoundCloud tokenizes the dash anyway.
        return _sc_search_entries(f"{artist} {song}" if song else artist, n=8)

    def _aud_all():
        return _audius_search_entries(
            f"{artist} {song}" if song else artist, n=8)

    def _yt_all():
        if _yt_breaker_open():
            logger.info("[MP3][SEARCH] YouTube skipped — breaker open (block wave)")
            return []
        out = []
        yt_queries = [f"{artist} {song} official audio", query] if song else [query]
        for yt_q in yt_queries:
            out.extend(_yt_search_entries(yt_q, n=5))
            if _yt_breaker_open():
                # First query tripped the breaker — don't waste a second call.
                break
        return out

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut_dur = ex.submit(_expected_duration, artist, song) if song else None
        fut_sc = ex.submit(_sc_all)
        fut_yt = ex.submit(_yt_all)
        fut_aud = ex.submit(_aud_all)
        expected_dur = fut_dur.result() if fut_dur else None
        sc_entries = fut_sc.result()
        yt_entries = fut_yt.result()
        aud_entries = fut_aud.result()

    seen_urls, scored = set(), []
    for provider, entries in (('SC', sc_entries), ('YT', yt_entries),
                              ('AU', aud_entries)):
        for e in entries:
            url = e.get('webpage_url') or e.get('url')
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            s = _score_candidate(e.get('title', ''), e.get('uploader', ''),
                                 int(e.get('duration', 0) or 0),
                                 artist, song, expected_dur)
            if s > -1e8:
                scored.append((s, provider, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    for s, provider, e in scored[:5]:
        logger.info(f"[MP3][RANK] score={s:.1f} | [{provider}] '{e.get('title')}' "
                    f"by '{e.get('uploader')}' | {int(e.get('duration', 0) or 0)}s")

    stage("⬇️ Downloading audio…")

    def _accept_downloaded(path: str, title_c: str, uploader_c: str, dur: int):
        size = os.path.getsize(path)
        if size < _MIN_SONG_BYTES:
            logger.warning(f"[MP3] too small ({size}B) — preview, skipping")
            cleanup_video(path)
            return None
        if size > 50 * 1024 * 1024:
            cleanup_video(path)
            return 'too_large'
        cached_path = _disk_cache_put(key, path)
        size_mb = round(size / 1024 / 1024, 1)
        logger.info(f"[MP3][SUCCESS] '{title_c}' | {size_mb}MB")
        return (True, (cached_path,
                       _build_success_msg(title_c, uploader_c, dur, size_mb),
                       title_c, uploader_c))

    def _try_download(url: str, rank_label: str):
        """Download one candidate with a hard time budget. Returns the mp3
        path, or raises on failure/timeout. Unique prefix per attempt so an
        abandoned (timed-out) download can't clobber the next attempt.

        Runs the download in a FORKED CHILD PROCESS, not a thread: threads
        can't be killed, so the old ThreadPoolExecutor approach could keep
        a stalled worker alive past the budget (round-13: a 45s cap that
        still waited). Here the child is terminate()d at the deadline —
        a stall can never hold a slot past _CANDIDATE_TIMEOUT_SECS.
        """
        import multiprocessing as _mp
        prefix = f'audio_{key[:10]}_{rank_label}'

        def _child(q, durl, pfx, label):
            # The fork inherits bot.py's SIGTERM/SIGINT handlers, which catch
            # the signal and shut down gracefully WITHOUT exiting — so the
            # parent's terminate() at the stall deadline left a lingering
            # ~80MB child instead of killing it. Reset to default so
            # terminate() really terminates.
            import signal as _signal
            _signal.signal(_signal.SIGTERM, _signal.SIG_DFL)
            _signal.signal(_signal.SIGINT, _signal.SIG_DFL)
            try:
                q.put(('ok', _download_url_to_mp3(durl, pfx, label=label)))
            except Exception as e:
                q.put(('err', f"{type(e).__name__}: {e}"))

        ctx = _mp.get_context('fork')
        q = ctx.Queue()
        p = ctx.Process(target=_child, args=(q, url, prefix, rank_label),
                        daemon=True)
        p.start()
        p.join(_CANDIDATE_TIMEOUT_SECS)
        if p.is_alive():
            p.terminate()
            p.join(5)
            if p.is_alive():
                # Last resort: SIGKILL can't be caught or ignored.
                p.kill()
                p.join(5)
            # Tidy partials the killed child may have left behind.
            for m in globmod.glob(os.path.join(os.getcwd(), f'{prefix}.*')):
                try:
                    os.remove(m)
                except OSError:
                    pass
            logger.warning(
                f"[MP3] {rank_label} hard-killed after "
                f"{_CANDIDATE_TIMEOUT_SECS}s stall — no lingering worker")
            raise TimeoutError(
                f"download stalled ({_CANDIDATE_TIMEOUT_SECS}s budget)")
        if not q.empty():
            status, payload = q.get()
            if status == 'ok':
                return payload
            raise RuntimeError(payload)
        raise RuntimeError("download child exited without a result")

    # Build the attempt list. During a YouTube block wave, a URL that
    # downloaded fine before is worth one direct shot (search is usually
    # what breaks, not the file hosts).
    attempts = []
    _bot_blocked = _yt_breaker_open()
    if _bot_blocked:
        stage("⚠️ YouTube is limiting us right now — trying the direct route…")
        win_url = _winurl_get(key)
        if win_url:
            logger.info(f"[MP3] block-wave retry of known-good URL for '{query}'")
            attempts.append((win_url, query, artist, 0, 'known-url'))

    # Try the top 3 scored candidates across ALL providers. YouTube 403s
    # and SoundCloud DRM blocks are often per-URL, so one more fallback
    # is usually the difference between success and "not available".
    for rank, (s, provider, e) in enumerate(scored[:3]):
        url = e.get('webpage_url') or e.get('url')
        attempts.append((url, e.get('title') or query,
                         e.get('uploader') or artist,
                         int(e.get('duration', 0) or 0),
                         f'{provider}-rank{rank+1}'))

    yt_watch_link = ("https://www.youtube.com/results?search_query=" +
                     requests.utils.quote(f"{artist} {song} official audio"
                                           if song else artist))

    _bot_blocked = _yt_breaker_open()
    _soft_wave_strikes = 0
    for url, title_c, uploader_c, dur, label in attempts:
        logger.info(f"[MP3] Trying {label}: '{title_c}'")
        try:
            path = _try_download(url, label.replace(' ', '_'))
        except Exception as ex:
            logger.info(f"[MP3] {label} failed: {type(ex).__name__}")
            if _is_block_error(ex):
                _bot_blocked = True
                _yt_trip_breaker(f"download {label}: {type(ex).__name__}")
            elif _is_soft_wave_error(ex):
                # One stall is bad luck; two in a row across different
                # candidates is a throttling wave. Stop burning minutes:
                # trip the breaker so this and later taps fail fast and
                # queue for the automatic retry instead.
                _soft_wave_strikes += 1
                if _soft_wave_strikes >= _WAVE_ABORT_STRIKES:
                    _bot_blocked = True
                    _yt_trip_breaker(
                        f"soft wave: {_soft_wave_strikes}x "
                        f"{type(ex).__name__} (last: {label})")
                    logger.warning(
                        f"[MP3] aborting '{query}' — soft wave detected, "
                        f"failing fast")
                    break
            else:
                _soft_wave_strikes = 0
            continue
        _soft_wave_strikes = 0
        res = _accept_downloaded(path, title_c, uploader_c, dur)
        if res == 'too_large':
            return False, ("❌ File Too Large\n━━━━━━━━━━━━━━━━━━━━━\n\nTelegram limit: 50MB.")
        if res:
            _winurl_note(key, url)
            return res

    logger.error(f"[MP3][FAIL] All providers exhausted for '{query}'")
    if _bot_blocked:
        fail_msg = (
            "❌ MP3 Not Available\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "YouTube is temporarily blocking downloads from this server "
            "(bot check), and SoundCloud had no playable copy.\n\n"
            f"🎧 Listen right now:\n{yt_watch_link}\n\n"
            "💡 This usually clears on its own — try again in a few minutes."
        )
    else:
        fail_msg = (
            "❌ MP3 Not Available\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Couldn't find a working audio source for this song.\n\n"
            f"🎧 Listen right now:\n{yt_watch_link}\n\n"
            "Please try again later."
        )
    _failure_note(key, fail_msg)
    return False, fail_msg




def download_youtube_audio(url: str) -> Tuple[bool, str]:
    """Download audio from a YouTube URL (legacy — prefer download_audio_for_song)."""
    try:
        logger.info(f"Starting MP3 download for URL: {url}")

        import hashlib
        file_prefix = 'audio_' + hashlib.md5(url.encode()).hexdigest()[:10]

        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': f'{file_prefix}.%(ext)s',
            'restrictfilenames': True,
            'socket_timeout': 30,
            'retries': 3,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0) or 0

                if duration > 600:
                    return False, (
                        "❌ Audio Too Long\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Max duration: 10 minutes.\n"
                        "This is {0}:{1:02d}.".format(duration // 60, duration % 60)
                    )

                ydl.download([url])

                mp3_path = os.path.join(os.getcwd(), f'{file_prefix}.mp3')
                if not os.path.exists(mp3_path):
                    matches = globmod.glob(os.path.join(os.getcwd(), f'{file_prefix}.*'))
                    matches = [m for m in matches if not m.endswith('.part')]
                    if matches:
                        mp3_path = matches[0]
                    else:
                        return False, "❌ Conversion Failed\n\nAudio extraction failed."

                file_size = os.path.getsize(mp3_path)
                file_size_mb = round(file_size / (1024 * 1024), 1)

                if file_size > 50 * 1024 * 1024:
                    cleanup_video(mp3_path)
                    return False, (
                        f"❌ File Too Large\n\nMP3 is {file_size_mb}MB (Telegram limit: 50MB)."
                    )

                title = info.get('title', 'Audio')
                uploader = info.get('uploader', 'Unknown')
                success_msg = (
                    f"🎵 MP3 Ready!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎤 {title}\n"
                    f"👤 {uploader}\n"
                    f"⏱️ {duration//60}:{duration%60:02d}  •  📦 {file_size_mb}MB\n\n"
                    f"🚀 Uploading..."
                )
                return True, (mp3_path, success_msg, title, uploader)

            except yt_dlp.utils.DownloadError as e:
                logger.error(f"yt-dlp audio DownloadError: {str(e)}")
                return False, "❌ MP3 Download Failed\n\nYouTube blocked the download."

    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        return False, "❌ MP3 Download Failed\n\nAn unexpected error occurred."

def cleanup_video(file_path: str) -> None:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file: {str(e)}")
