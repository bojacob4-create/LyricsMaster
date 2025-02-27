import logging
from typing import Optional, Dict, Tuple
from pytube import YouTube
import os
import trafilatura
import re

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

        # First try to fetch the page content to verify accessibility
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return False, (
                "❌ Could not access the video.\n"
                "Please check if the video exists and is public! 🔍"
            )

        # Create YouTube object with custom settings
        yt = YouTube(
            url,
            use_oauth=False,
            allow_oauth_cache=False
        )
        yt.bypass_age_gate()

        logger.info(f"Successfully accessed video: {yt.title}")

        # Get the best progressive stream (includes both video and audio)
        video = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first()

        if not video:
            logger.error("No suitable video stream found")
            return False, (
                "❌ No suitable video stream found.\n"
                "Please try another video! 🎬"
            )

        # Check file size
        if video.filesize > 50 * 1024 * 1024:  # 50MB in bytes
            logger.warning(f"Video size {video.filesize/(1024*1024):.1f}MB exceeds 50MB limit")
            return False, (
                "❌ Video is too large for Telegram (>50MB).\n"
                "Please try a shorter video! 🎬"
            )

        # Try downloading with multiple attempts
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                logger.info(f"Download attempt {attempt + 1} of {max_attempts}")
                video.download()
                file_path = video.default_filename
                logger.info(f"Successfully downloaded to: {file_path}")

                # Format success message
                success_msg = (
                    "✅ Video downloaded successfully!\n\n"
                    f"📽️ Title: {yt.title}\n"
                    f"👤 Channel: {yt.author}\n"
                    f"⏱️ Length: {yt.length//60}:{yt.length%60:02d}\n"
                    f"👀 Views: {yt.views:,}\n"
                    f"📦 Size: {round(video.filesize / (1024 * 1024), 1)}MB\n\n"
                    "🚀 Uploading to Telegram..."
                )

                return True, (file_path, success_msg)

            except Exception as e:
                logger.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_attempts - 1:
                    continue

                # If all attempts failed, try a lower resolution
                video = yt.streams.filter(
                    progressive=True,
                    file_extension='mp4',
                    resolution='720p'
                ).first()

                if not video:
                    return False, (
                        "❌ Download failed after multiple attempts.\n"
                        "Please try another video or try again later! 🔄"
                    )

                # One final attempt with lower resolution
                try:
                    video.download()
                    file_path = video.default_filename
                    logger.info(f"Successfully downloaded lower resolution to: {file_path}")

                    success_msg = (
                        "✅ Video downloaded successfully (720p)!\n\n"
                        f"📽️ Title: {yt.title}\n"
                        f"👤 Channel: {yt.author}\n"
                        f"⏱️ Length: {yt.length//60}:{yt.length%60:02d}\n"
                        f"👀 Views: {yt.views:,}\n"
                        f"📦 Size: {round(video.filesize / (1024 * 1024), 1)}MB\n\n"
                        "🚀 Uploading to Telegram..."
                    )

                    return True, (file_path, success_msg)

                except Exception as final_e:
                    logger.error(f"Final download attempt failed: {str(final_e)}")
                    return False, (
                        "❌ Download failed.\n"
                        "This could be because:\n"
                        "• The video is restricted\n"
                        "• Server is busy\n"
                        "Please try another video or wait a few minutes! 🕒"
                    )

    except Exception as e:
        error_details = str(e).lower()
        logger.error(f"Error downloading YouTube video: {error_details}")

        if "age restricted" in error_details:
            return False, (
                "😓 Sorry, this video is age-restricted.\n"
                "Please try a different video that's not age-restricted! 🎬"
            )
        elif "private video" in error_details:
            return False, (
                "❌ This video is private.\n"
                "Please try a public video instead! 🎬"
            )
        elif "not available" in error_details:
            return False, (
                "❌ This video is not available.\n"
                "Please check:\n"
                "• The video still exists\n"
                "• The video is public\n"
                "• Try another video"
            )
        else:
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