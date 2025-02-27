import logging
from typing import Optional, Dict, Tuple
from pytube import YouTube
import os

logger = logging.getLogger(__name__)

def download_youtube_video(url: str) -> Tuple[bool, str]:
    """Download a YouTube video and return a status message."""
    try:
        logger.info(f"Starting download process for URL: {url}")

        # Create YouTube object with custom user agent
        yt = YouTube(
            url,
            use_oauth=False,  # Disable OAuth
            allow_oauth_cache=False
        )
        yt.bypass_age_gate()  # Try to bypass age restrictions

        logger.info(f"Successfully created YouTube object for video: {yt.title}")

        # Get video info before downloading
        info = {
            'title': yt.title,
            'author': yt.author,
            'length': f"{yt.length//60}:{yt.length%60:02d}",
            'views': yt.views
        }

        logger.info("Fetching available streams...")
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

        # Check if file size is reasonable (less than 50MB for Telegram)
        if video.filesize > 50 * 1024 * 1024:  # 50MB in bytes
            logger.warning(f"Video size {video.filesize/(1024*1024):.1f}MB exceeds 50MB limit")
            return False, (
                "❌ Video is too large for Telegram (>50MB).\n"
                "Please try a shorter video! 🎬"
            )

        # Download video with retry mechanism
        try:
            logger.info(f"Starting download for video: {info['title']}")
            video.download()
            file_path = video.default_filename
            logger.info(f"Successfully downloaded to: {file_path}")
        except Exception as download_error:
            logger.error(f"First download attempt failed: {str(download_error)}")
            # Retry with different stream
            logger.info("Attempting retry with 720p resolution...")
            video = yt.streams.filter(
                progressive=True,
                file_extension='mp4',
                resolution='720p'
            ).first()
            if not video:
                return False, "❌ Download failed. Please try another video."

            video.download()
            file_path = video.default_filename
            logger.info(f"Successfully downloaded to: {file_path} on second attempt")

        # Format success message
        success_msg = (
            "✅ Video downloaded successfully!\n\n"
            f"📽️ Title: {info['title']}\n"
            f"👤 Channel: {info['author']}\n"
            f"⏱️ Length: {info['length']}\n"
            f"👀 Views: {info['views']:,}\n"
            f"📦 Size: {round(video.filesize / (1024 * 1024), 1)}MB\n\n"
            "🚀 Uploading to Telegram..."
        )

        return True, (file_path, success_msg)

    except Exception as e:
        error_details = str(e)
        logger.error(f"Error downloading YouTube video: {error_details}")

        if "age restricted" in error_details.lower():
            return False, (
                "😓 Sorry, this video is age-restricted.\n"
                "Please try a different video that's not age-restricted! 🎬"
            )
        elif "private video" in error_details.lower():
            return False, (
                "❌ This video is private.\n"
                "Please try a public video instead! 🎬"
            )
        elif "not available" in error_details.lower():
            return False, (
                "❌ This video is not available.\n"
                "Please check:\n"
                "• The video still exists\n"
                "• The video is public\n"
                "• Try another video"
            )
        else:
            return False, (
                "😓 Something went wrong while downloading.\n"
                "Please check:\n"
                "• The video URL is valid\n"
                "• The video is not age-restricted\n"
                "• Try another video\n"
                "Error: HTTP Error 403: Forbidden"
            )

def cleanup_video(file_path: str) -> None:
    """Clean up downloaded video file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up video file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up video file: {str(e)}")