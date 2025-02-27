import logging
from typing import Optional, Dict, Tuple
from pytube import YouTube
import os

logger = logging.getLogger(__name__)

def download_youtube_video(url: str) -> Tuple[bool, str]:
    """
    Download a YouTube video and return a status message.

    Args:
        url (str): YouTube video URL

    Returns:
        Tuple[bool, str]: (success status, message)
    """
    try:
        # Create YouTube object with custom user agent
        yt = YouTube(
            url,
            use_oauth=True,
            allow_oauth_cache=True
        )

        # Get video info before downloading
        info = {
            'title': yt.title,
            'author': yt.author,
            'length': f"{yt.length//60}:{yt.length%60:02d}",
            'views': yt.views
        }

        # Get the best progressive stream (includes both video and audio)
        video = yt.streams.filter(
            progressive=True,
            file_extension='mp4'
        ).order_by('resolution').desc().first()

        if not video:
            return False, (
                "❌ No suitable video stream found.\n"
                "Please try another video! 🎬"
            )

        # Check if file size is reasonable (less than 50MB for Telegram)
        if video.filesize > 50 * 1024 * 1024:  # 50MB in bytes
            return False, (
                "❌ Video is too large for Telegram (>50MB).\n"
                "Please try a shorter video! 🎬"
            )

        # Download video with retry mechanism
        try:
            video.download()
            file_path = video.default_filename
        except Exception as download_error:
            logger.error(f"First download attempt failed: {str(download_error)}")
            # Retry with different stream
            video = yt.streams.filter(
                progressive=True,
                file_extension='mp4',
                resolution='720p'
            ).first()
            if not video:
                return False, "❌ Download failed. Please try another video."
            video.download()
            file_path = video.default_filename

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

        if "403" in error_details:
            return False, (
                "😓 Sorry, this video is not accessible.\n"
                "This could be because:\n"
                "• The video is age-restricted\n"
                "• The video is private\n"
                "• YouTube's security measures\n\n"
                "Please try another video! 🎬"
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
                "Please try:\n"
                "• Using a different video\n"
                "• Checking the URL is correct\n"
                "• Waiting a few minutes\n\n"
                f"Error: {str(e)}"
            )

def cleanup_video(file_path: str) -> None:
    """Clean up downloaded video file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up video file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up video file: {str(e)}")