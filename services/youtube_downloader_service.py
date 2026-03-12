import logging
from typing import Optional, Dict, Tuple
import os
import re
import yt_dlp
import unicodedata
import string
import glob as globmod

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

def _try_audio_download(source_query: str, file_prefix: str) -> Tuple[bool, any]:
    """Attempt audio download from a single source query."""
    output_template = f'{file_prefix}.%(ext)s'
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': output_template,
        'restrictfilenames': True,
        'socket_timeout': 30,
        'retries': 2,
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
        info = ydl.extract_info(source_query, download=False)
        if isinstance(info, dict) and info.get('entries'):
            info = info['entries'][0]
        duration = info.get('duration', 0) or 0
        if duration > 600:
            raise ValueError(f"too_long:{duration}")
        ydl.download([source_query])
        mp3_path = os.path.join(os.getcwd(), f'{file_prefix}.mp3')
        if not os.path.exists(mp3_path):
            matches = globmod.glob(os.path.join(os.getcwd(), f'{file_prefix}.*'))
            matches = [m for m in matches if not m.endswith('.part')]
            if matches:
                mp3_path = matches[0]
            else:
                raise FileNotFoundError("audio file not found after download")
        return True, (mp3_path, info.get('title', 'Audio'), info.get('uploader', 'Unknown'), duration)


def download_audio_for_song(artist: str, song: str) -> Tuple[bool, any]:
    """Download MP3 for a song by trying multiple audio sources in order."""
    import hashlib
    query = f"{artist} - {song}" if song else artist
    file_prefix = 'audio_' + hashlib.md5(query.encode()).hexdigest()[:10]

    sources = [
        f"ytsearch1:{query}",
        f"scsearch1:{query}",
        f"ytsearch1:{song} {artist}" if song else None,
    ]
    sources = [s for s in sources if s]

    for source in sources:
        try:
            logger.info(f"MP3: trying source '{source}'")
            ok, data = _try_audio_download(source, file_prefix)
            if ok:
                mp3_path, title, uploader, duration = data
                file_size = os.path.getsize(mp3_path)
                file_size_mb = round(file_size / (1024 * 1024), 1)
                if file_size > 50 * 1024 * 1024:
                    cleanup_video(mp3_path)
                    return False, (
                        "❌ File Too Large\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"MP3 is {file_size_mb}MB (Telegram limit: 50MB)."
                    )
                success_msg = (
                    f"🎵 MP3 Ready!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎤 {title}\n"
                    f"👤 {uploader}\n"
                    f"⏱️ {duration//60}:{duration%60:02d}  •  📦 {file_size_mb}MB\n\n"
                    f"🚀 Uploading..."
                )
                return True, (mp3_path, success_msg, title, uploader)
        except ValueError as e:
            if str(e).startswith("too_long:"):
                duration = int(str(e).split(":")[1])
                return False, (
                    "❌ Audio Too Long\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"This track is {duration//60}:{duration%60:02d}.\n"
                    "Max allowed: 10 minutes."
                )
        except Exception as e:
            logger.warning(f"MP3 source '{source}' failed: {e}")
            continue

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
