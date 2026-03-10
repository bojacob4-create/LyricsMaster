import logging
from typing import Optional, Dict, Tuple
import os
import re
import yt_dlp
import unicodedata
import string

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to only use ASCII characters."""
    # Convert to ASCII, removing non-ASCII characters
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()
    # Keep only alphanumeric characters, dashes, and underscores
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in filename if c in valid_chars)
    # Remove spaces
    filename = filename.replace(' ', '_')
    return filename or 'video'  # Return 'video' if filename becomes empty

def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/)([^&?/]+)',
        r'youtube.com/shorts/([^&?/]+)'
    ]
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    return None

def validate_youtube_url(url: str) -> bool:
    """Validate if the URL is a valid YouTube video URL."""
    video_id = extract_video_id(url)
    if not video_id:
        return False
    return True

def download_youtube_video(url: str) -> Tuple[bool, str]:
    """Download a YouTube video and return a status message."""
    try:
        logger.info(f"Starting download process for URL: {url}")

        # Validate URL first
        if not validate_youtube_url(url):
            return False, (
                "❌ Invalid YouTube URL.\n"
                "Please provide a valid YouTube video URL! 🎬\n"
                "Example: https://youtube.com/watch?v=..."
            )

        # Generate a safe output template
        video_id = extract_video_id(url)
        output_template = f'youtube_{video_id}.%(ext)s'

        # Configure yt-dlp options
        ydl_opts = {
            'format': 'best[filesize<50M]',  # Best format under 50MB
            'noplaylist': True,  # Single video only
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'outtmpl': output_template,  # Use safe output template
            'restrictfilenames': True,  # Restrict filenames to ASCII
        }

        # Get video info first
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if info.get('filesize', 0) > 50 * 1024 * 1024:  # 50MB
                    return False, (
                        "❌ Video is too large for Telegram (>50MB).\n"
                        "Please try a shorter video! 🎬"
                    )

                ydl.download([url])

                import glob as globmod
                matches = globmod.glob(os.path.join(os.getcwd(), f'youtube_{video_id}.*'))
                if not matches:
                    logger.error(f"No downloaded file found for video_id: {video_id}")
                    return False, (
                        "❌ Download Failed\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "The video downloaded but the file couldn't be located.\n"
                        "This usually means the format was incompatible.\n"
                        "Try a different video."
                    )

                file_path = matches[0]
                duration = info.get('duration', 0) or 0
                views = info.get('view_count', 0) or 0
                file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 1)

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

                if "private video" in error_msg:
                    reason = "This video is private and can't be accessed."
                elif "age restricted" in error_msg or "age-restricted" in error_msg:
                    reason = "This video is age-restricted. The bot can't bypass age verification."
                elif "copyright" in error_msg:
                    reason = "This video is blocked due to copyright restrictions."
                elif "not available" in error_msg or "unavailable" in error_msg:
                    reason = "This video is not available (may be region-locked or deleted)."
                elif "sign in" in error_msg or "login" in error_msg:
                    reason = "This video requires authentication to access."
                elif "429" in error_msg or "too many" in error_msg:
                    reason = "YouTube is rate-limiting requests. Please wait a few minutes."
                else:
                    reason = "YouTube blocked the download. This often happens with music videos due to DRM protection."

                return False, (
                    f"❌ Download Failed\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Reason: {reason}\n\n"
                    f"💡 Tips:\n"
                    f"• Try a different video\n"
                    f"• Shorter videos work better\n"
                    f"• Unofficial uploads are easier to download"
                )

    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        return False, (
            "❌ Download Failed\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "An unexpected error occurred during download.\n\n"
            "💡 Tips:\n"
            "• Check the URL is correct\n"
            "• Try a different video\n"
            "• Wait a minute and retry"
        )

def cleanup_video(file_path: str) -> None:
    """Clean up downloaded video file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up video file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up video file: {str(e)}")