import logging
from typing import Optional, Dict, Tuple
import os
import re
import yt_dlp

logger = logging.getLogger(__name__)

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

        # Configure yt-dlp options
        ydl_opts = {
            'format': 'best[filesize<50M]',  # Best format under 50MB
            'noplaylist': True,  # Single video only
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
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

                # Download the video
                ydl.download([url])

                # Get the downloaded file path
                file_path = os.path.join(os.getcwd(), f"{info['title']}.mp4")

                success_msg = (
                    "✅ Video downloaded successfully!\n\n"
                    f"📽️ Title: {info['title']}\n"
                    f"👤 Channel: {info['uploader']}\n"
                    f"⏱️ Length: {info['duration']//60}:{info['duration']%60:02d}\n"
                    f"👀 Views: {info.get('view_count', 0):,}\n"
                    f"📦 Size: {round(os.path.getsize(file_path) / (1024 * 1024), 1)}MB\n\n"
                    "🚀 Uploading to Telegram..."
                )

                return True, (file_path, success_msg)

            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e).lower()
                if "private video" in error_msg:
                    return False, (
                        "❌ This video is private.\n"
                        "Please try a public video instead! 🎬"
                    )
                elif "age restricted" in error_msg:
                    return False, (
                        "😓 Sorry, this video is age-restricted.\n"
                        "Please try a different video that's not age-restricted! 🎬"
                    )
                else:
                    return False, (
                        "❌ Download failed.\n"
                        "This could be because:\n"
                        "• The video is restricted\n"
                        "• The video is too long\n"
                        "Please try another video! 🔄"
                    )

    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        return False, (
            "😓 Download failed.\n"
            "Please try:\n"
            "• A different video\n"
            "• Checking if the video is public\n"
            "• Using a shorter video\n"
            "• Waiting a few minutes"
        )

def cleanup_video(file_path: str) -> None:
    """Clean up downloaded video file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up video file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up video file: {str(e)}")