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

def download_youtube_video(url: str) -> Tuple[bool, str]:
    try:
        logger.info(f"Starting download process for URL: {url}")

        if not validate_youtube_url(url):
            return False, (
                "❌ Invalid YouTube URL\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please provide a valid YouTube link:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/..."
            )

        video_id = extract_video_id(url)
        output_template = f'youtube_{video_id}.%(ext)s'

        ydl_opts = {
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'socket_timeout': 30,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0) or 0

                if duration > 600:
                    return False, (
                        "❌ Video Too Long\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Max duration: 10 minutes.\n"
                        "This video is {0}:{1:02d}.\n"
                        "Try a shorter video.".format(duration // 60, duration % 60)
                    )

                ydl.download([url])

                matches = globmod.glob(os.path.join(os.getcwd(), f'youtube_{video_id}.*'))
                matches = [m for m in matches if not m.endswith('.part')]
                if not matches:
                    logger.error(f"No downloaded file found for video_id: {video_id}")
                    return False, (
                        "❌ Download Failed\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "The file couldn't be saved.\n"
                        "Try a different video."
                    )

                file_path = matches[0]
                file_size = os.path.getsize(file_path)
                file_size_mb = round(file_size / (1024 * 1024), 1)

                if file_size > 50 * 1024 * 1024:
                    cleanup_video(file_path)
                    return False, (
                        "❌ File Too Large\n"
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

            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e).lower()
                logger.error(f"yt-dlp DownloadError: {str(e)}")

                if "private video" in error_msg or "private" in error_msg:
                    reason = "This video is private."
                elif "age restricted" in error_msg or "age-restricted" in error_msg or "sign in to confirm" in error_msg:
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
                    f"❌ Download Failed\n"
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
            "❌ Download Failed\n"
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

# Title markers that (almost) always mean "not the original". Penalized
# unless the requested song title itself contains the marker.
_REMIX_MARKERS = (
    'remix', 'cover', 'sped up', 'spedup', 'slowed', 'nightcore', 'mashup',
    'unplugged', 'acoustic', '8d', 'flip', 'bootleg', 'extended',
    'karaoke', 'instrumental', 'reverb', 'tiktok',
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
        return []
    entries = []
    if isinstance(meta, dict):
        entries = meta.get('entries', []) or []
    out = [e for e in entries if e.get('url')]
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
        os.makedirs(MP3_CACHE_DIR, exist_ok=True)
        data = {}
        try:
            with open(_MP3_FILEID_JSON, 'r', encoding='utf-8') as f:
                data = _json.load(f)
        except Exception:
            pass
        data[_mp3_cache_key(artist, song)] = file_id
        with open(_MP3_FILEID_JSON, 'w', encoding='utf-8') as f:
            _json.dump(data, f)
        logger.info(f"[MP3][CACHE] file_id stored for '{artist} - {song}'")
    except Exception as e:
        logger.debug(f"[MP3][CACHE] file_id store failed: {type(e).__name__}")


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
_PERMANENT_DL_ERRORS = ('drm', 'private video', 'age-restricted',
                        'age restricted', 'copyright', 'unavailable',
                        'not available', 'requires authentication',
                        'sign in to confirm')


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
                raise
        except Exception as e:
            last_err = e
            logger.warning(f"[MP3][DOWNLOAD] Error | provider={label} "
                           f"| client={client}: {type(e).__name__}: {e}")
        time.sleep(2)

    if last_err is not None:
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

    # ── Tier 2: fresh resolve (providers run in parallel) ──────────────────
    # SoundCloud + YouTube searches and the lrclib duration lookup are
    # independent — run them together, then score ALL candidates globally
    # and download only the best. Audiomack's API is dead (returns HTML),
    # so it was dropped.
    stage("🔍 Finding the original track…")

    def _sc_all():
        # One query is enough — SoundCloud tokenizes the dash anyway.
        return _sc_search_entries(f"{artist} {song}" if song else artist, n=8)

    def _yt_all():
        out = []
        yt_queries = [f"{artist} {song} official audio", query] if song else [query]
        for yt_q in yt_queries:
            out.extend(_yt_search_entries(yt_q, n=5))
        return out

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        fut_dur = ex.submit(_expected_duration, artist, song) if song else None
        fut_sc = ex.submit(_sc_all)
        fut_yt = ex.submit(_yt_all)
        expected_dur = fut_dur.result() if fut_dur else None
        sc_entries = fut_sc.result()
        yt_entries = fut_yt.result()

    seen_urls, scored = set(), []
    for provider, entries in (('SC', sc_entries), ('YT', yt_entries)):
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
    file_prefix = 'audio_' + key[:10]

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

    # Try the top 3 scored candidates across ALL providers. YouTube 403s
    # and SoundCloud DRM blocks are often per-URL, so one more fallback
    # is usually the difference between success and "not available".
    for rank, (s, provider, e) in enumerate(scored[:3]):
        url = e.get('webpage_url') or e.get('url')
        title_c = e.get('title') or query
        uploader_c = e.get('uploader') or artist
        dur = int(e.get('duration', 0) or 0)
        logger.info(f"[MP3] Trying rank {rank+1} [{provider}] (score={s:.1f}): '{title_c}'")
        try:
            path = _download_url_to_mp3(url, file_prefix, label=f'{provider}-rank{rank+1}')
        except Exception as ex:
            logger.info(f"[MP3] rank {rank+1} failed: {type(ex).__name__}")
            continue
        res = _accept_downloaded(path, title_c, uploader_c, dur)
        if res == 'too_large':
            return False, ("❌ File Too Large\n━━━━━━━━━━━━━━━━━━━━━\n\nTelegram limit: 50MB.")
        if res:
            return res

    logger.error(f"[MP3][FAIL] All providers exhausted for '{query}'")
    return False, (
        "❌ MP3 Not Available\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Couldn't find a working audio source for this song.\n"
        "Please try again later."
    )




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
