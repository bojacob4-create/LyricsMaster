import logging
from typing import Optional, Dict, Tuple
import os
import re
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

# ── MP3 constants ────────────────────────────────────────────────────────────
_MIN_SONG_BYTES = 800_000     # < 800 KB = likely a short preview, skip it
_MIN_SONG_SECS  = 90          # < 90 s duration in metadata = likely a preview


def _clean_song_title(title: str) -> str:
    """Strip features/parentheticals for simpler searches."""
    title = re.sub(r'\s*[\(\[](feat|ft|with|prod|remix)[^\)\]]*[\)\]]', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*-\s*(feat|ft)\.?\s+.+$', '', title, flags=re.IGNORECASE)
    return title.strip()


def _clean_artist_hint(artist: str) -> str:
    """Strip 'feat. ...' from artist name so 'Rihanna feat. JAY-Z' matches 'Rihanna'."""
    return re.sub(r'\s*(feat\.|ft\.|featuring).*$', '', artist, flags=re.IGNORECASE).strip()


def _sc_search_ranked(query: str, n: int = 5, artist_hint: str = '') -> list:
    """
    Search SoundCloud for top N results and return a RANKED LIST of candidates to try.
    Priority order:
      1. Official artist uploads (uploader matches artist_hint) with duration >= _MIN_SONG_SECS
      2. Other full-length uploads (duration >= _MIN_SONG_SECS), sorted longest-first
    Returns a list of yt-dlp entry dicts (may be empty).
    """
    logger.info(f"[MP3][SEARCH] SoundCloud scsearch{n}: '{query}'")
    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'socket_timeout': 15}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(f'scsearch{n}:{query}', download=False)
    except Exception as e:
        logger.warning(f"[MP3][SEARCH] SoundCloud search error: {type(e).__name__}: {e}")
        return []

    entries = []
    if isinstance(meta, dict):
        entries = meta.get('entries', []) or []
        if not entries and meta.get('id'):
            entries = [meta]

    if not entries:
        logger.warning(f"[MP3][SEARCH] No results for '{query}'")
        return []

    logger.info(f"[MP3][SEARCH] Got {len(entries)} result(s):")
    for i, e in enumerate(entries):
        dur = int(e.get('duration', 0) or 0)
        logger.info(f"[MP3][SEARCH]   [{i+1}] '{e.get('title')}' by '{e.get('uploader')}' "
                    f"| {dur}s | {e.get('webpage_url', e.get('url', '?'))}")

    full_entries = [e for e in entries if int(e.get('duration', 0) or 0) >= _MIN_SONG_SECS]
    if not full_entries:
        logger.warning(f"[MP3][SEARCH] No full-length results (all < {_MIN_SONG_SECS}s) for '{query}'")
        return []

    hint_low = artist_hint.lower() if artist_hint else ''
    official, others = [], []
    for e in full_entries:
        uploader_low = (e.get('uploader') or '').lower()
        if hint_low and (hint_low in uploader_low or uploader_low in hint_low):
            official.append(e)
        else:
            others.append(e)

    others_sorted = sorted(others, key=lambda e: int(e.get('duration', 0) or 0), reverse=True)
    ranked = official + others_sorted
    logger.info(f"[MP3][SEARCH] Ranked {len(ranked)} candidates "
                f"({len(official)} official, {len(others_sorted)} others)")
    return ranked


def _search_audiomack_url(artist: str, song: str) -> Optional[str]:
    """Search Audiomack unofficial API and return the track page URL, or None."""
    logger.info(f"[MP3][SEARCH] Audiomack: '{artist} - {song}'")
    query = f"{artist} {song}"
    try:
        r = requests.get(
            'https://audiomack.com/api/v1/music/search',
            params={'q': query, 'type': 'song', 'limit': 3},
            timeout=6,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
        )
        if r.status_code == 200:
            results = r.json().get('results', {})
            if isinstance(results, dict):
                results = results.get('results', [])
            if results:
                track = results[0]
                uploader_slug = (track.get('uploader') or {}).get('url_slug', '')
                song_slug = track.get('url_slug', '')
                if uploader_slug and song_slug:
                    url = f"https://audiomack.com/{uploader_slug}/song/{song_slug}"
                    logger.info(f"[MP3][SEARCH] Audiomack found: {url}")
                    return url
    except Exception as e:
        logger.debug(f"[MP3][SEARCH] Audiomack error: {type(e).__name__}: {e}")
    logger.info(f"[MP3][SEARCH] Audiomack: no match")
    return None


def _search_archive_org(artist: str, song: str) -> Optional[str]:
    """Search Archive.org for a music track. Returns a page URL or None."""
    logger.info(f"[MP3][SEARCH] Archive.org: '{artist} - {song}'")
    try:
        r = requests.get(
            'https://archive.org/advancedsearch.php',
            params={
                'q': f'title:"{song}" creator:"{artist}" mediatype:audio',
                'fl[]': 'identifier,title,creator',
                'output': 'json',
                'rows': '3',
                'sort[]': 'downloads desc',
            },
            timeout=6,
            headers={'User-Agent': 'LyricsMasterBot/1.0'},
        )
        if r.status_code == 200:
            docs = r.json().get('response', {}).get('docs', [])
            if docs:
                identifier = docs[0].get('identifier', '')
                creator = docs[0].get('creator', '')
                title = docs[0].get('title', '')
                logger.info(f"[MP3][SEARCH] Archive.org match: id='{identifier}' "
                            f"title='{title}' creator='{creator}'")
                return f"https://archive.org/details/{identifier}"
    except Exception as e:
        logger.debug(f"[MP3][SEARCH] Archive.org error: {type(e).__name__}: {e}")
    logger.info(f"[MP3][SEARCH] Archive.org: no match")
    return None


def _download_url_to_mp3(download_url: str, file_prefix: str, label: str) -> str:
    """
    Download audio from a resolved URL and convert to MP3.
    Returns the local mp3 file path on success. Raises on failure.
    """
    logger.info(f"[MP3][DOWNLOAD] Starting | provider={label} | url='{download_url}'")
    output_template = f'{file_prefix}.%(ext)s'
    dl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': output_template,
        'restrictfilenames': True,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 5,
        'skip_unavailable_fragments': False,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ret = ydl.download([download_url])
        if ret != 0:
            raise RuntimeError(f"yt-dlp returned non-zero code: {ret}")
    except yt_dlp.utils.DownloadError as de:
        logger.warning(f"[MP3][DOWNLOAD] DownloadError | provider={label}: {de}")
        raise
    except Exception as e:
        logger.warning(f"[MP3][DOWNLOAD] Error | provider={label}: {type(e).__name__}: {e}")
        raise

    mp3_path = os.path.join(os.getcwd(), f'{file_prefix}.mp3')
    if not os.path.exists(mp3_path):
        matches = [m for m in globmod.glob(os.path.join(os.getcwd(), f'{file_prefix}.*'))
                   if not m.endswith('.part')]
        if matches:
            mp3_path = matches[0]
            logger.info(f"[MP3][FILE] Found at alternate path: '{mp3_path}'")
        else:
            logger.warning(f"[MP3][FILE] No file found after download | provider={label}")
            raise FileNotFoundError(f"mp3 not found after download via {label}")

    size_bytes = os.path.getsize(mp3_path)
    logger.info(f"[MP3][FILE] OK | provider={label} | path='{mp3_path}' "
                f"| size={round(size_bytes/1024/1024, 2)}MB")
    return mp3_path


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


def download_audio_for_song(artist: str, song: str) -> Tuple[bool, any]:
    """
    Download MP3. Providers in order:
      1. SoundCloud — searches 5 results, tries EACH candidate until one succeeds
         (official artist upload first, then others sorted by length)
      2. Audiomack fallback

    Key design: if a SC track downloads too small (preview), we continue to the
    NEXT candidate in the same search result set — not just the next query.
    This ensures fan uploads / remixes are tried when the official track is preview-only.
    """
    import hashlib
    query = f"{artist} - {song}" if song else artist
    file_prefix = 'audio_' + hashlib.md5(query.encode()).hexdigest()[:10]
    simple_song = _clean_song_title(song) if song else ''
    # Strip 'feat. ...' so 'Rihanna feat. JAY-Z' matches uploader 'Rihanna'
    artist_hint = _clean_artist_hint(artist)

    logger.info(f"[MP3][START] artist='{artist}' | song='{song}' | "
                f"artist_hint='{artist_hint}' | query='{query}'")

    # ── Provider 1: SoundCloud ────────────────────────────────────────────────
    sc_queries = [query]
    if song:
        sc_queries.append(f"{song} {artist_hint}")
    if simple_song and simple_song != song:
        sc_queries.append(f"{artist_hint} - {simple_song}")
        sc_queries.append(f"{simple_song} {artist_hint}")

    tried_urls: set = set()

    for sc_q in sc_queries:
        logger.info(f"[MP3][P1-SC] Query: '{sc_q}'")
        candidates = _sc_search_ranked(sc_q, n=5, artist_hint=artist_hint)

        if not candidates:
            logger.info(f"[MP3][P1-SC] No candidates from '{sc_q}'")
            continue

        for idx, candidate in enumerate(candidates):
            dl_url = candidate.get('webpage_url') or candidate.get('url')
            if not dl_url:
                logger.warning(f"[MP3][P1-SC] Candidate {idx+1}: no URL, skipping")
                continue
            if dl_url in tried_urls:
                logger.info(f"[MP3][P1-SC] Candidate {idx+1}: already tried '{dl_url}', skipping")
                continue
            tried_urls.add(dl_url)

            dur = int(candidate.get('duration', 0) or 0)
            title_c = candidate.get('title', song)
            uploader_c = candidate.get('uploader', artist)
            logger.info(f"[MP3][P1-SC] Trying candidate {idx+1}/{len(candidates)}: "
                        f"'{title_c}' by '{uploader_c}' ({dur}s)")

            try:
                mp3_path = _download_url_to_mp3(dl_url, file_prefix, label=f'SC[{idx+1}]')
            except Exception as e:
                logger.info(f"[MP3][P1-SC] Candidate {idx+1} download failed: "
                            f"{type(e).__name__}: {e}")
                continue

            file_size = os.path.getsize(mp3_path)
            if file_size < _MIN_SONG_BYTES:
                logger.warning(f"[MP3][P1-SC] Candidate {idx+1} too small "
                               f"({file_size} bytes < {_MIN_SONG_BYTES}) — preview, skipping")
                cleanup_video(mp3_path)
                continue

            if file_size > 50 * 1024 * 1024:
                cleanup_video(mp3_path)
                return False, ("❌ File Too Large\n━━━━━━━━━━━━━━━━━━━━━\n\nTelegram limit: 50MB.")

            file_size_mb = round(file_size / 1024 / 1024, 1)
            logger.info(f"[MP3][P1-SC] SUCCESS | candidate={idx+1} | "
                        f"title='{title_c}' | {file_size_mb}MB")
            return True, (mp3_path,
                          _build_success_msg(title_c, uploader_c, dur, file_size_mb),
                          title_c, uploader_c)

        logger.info(f"[MP3][P1-SC] All candidates from '{sc_q}' exhausted")

    logger.info(f"[MP3][P1-SC] All SC queries exhausted — moving to Provider 2")

    # ── Provider 2: Audiomack ─────────────────────────────────────────────────
    am_url = _search_audiomack_url(artist, song)
    if am_url:
        resolve_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'socket_timeout': 12}
        try:
            with yt_dlp.YoutubeDL(resolve_opts) as ydl:
                am_meta = ydl.extract_info(am_url, download=False)
            dl_url = (am_meta or {}).get('webpage_url') or am_url
            mp3_path = _download_url_to_mp3(dl_url, file_prefix, label='Audiomack')
            dur = int((am_meta or {}).get('duration', 0) or 0)
            title = (am_meta or {}).get('title', song)
            uploader = (am_meta or {}).get('uploader', artist)
            file_size_mb = round(os.path.getsize(mp3_path) / 1024 / 1024, 1)
            logger.info(f"[MP3][P2-AM] SUCCESS | title='{title}' | {file_size_mb}MB")
            return True, (mp3_path, _build_success_msg(title, uploader, dur, file_size_mb), title, uploader)
        except Exception as e:
            logger.warning(f"[MP3][P2-AM] Failed: {type(e).__name__}: {e}")
    else:
        logger.info(f"[MP3][P2-AM] No Audiomack URL — skipping")

    # ── All providers exhausted ───────────────────────────────────────────────
    logger.error(f"[MP3][FAIL] All providers exhausted for '{artist} - {song}'")
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
