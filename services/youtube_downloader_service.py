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
        # Create YouTube object
        yt = YouTube(url)
        
        # Get the best progressive stream (includes both video and audio)
        video = yt.streams.get_highest_resolution()
        
        # Get video info
        info = {
            'title': yt.title,
            'author': yt.author,
            'length': f"{yt.length//60}:{yt.length%60:02d}",
            'views': yt.views,
            'size_mb': round(video.filesize / (1024 * 1024), 1)
        }
        
        # Check if file size is reasonable (less than 50MB for Telegram)
        if video.filesize > 50 * 1024 * 1024:  # 50MB in bytes
            return False, (
                "❌ Video is too large for Telegram (>50MB).\n"
                "Please try a shorter video! 🎬"
            )
            
        # Download video
        video.download()
        file_path = video.default_filename
        
        # Format success message
        success_msg = (
            "✅ Video downloaded successfully!\n\n"
            f"📽️ Title: {info['title']}\n"
            f"👤 Channel: {info['author']}\n"
            f"⏱️ Length: {info['length']}\n"
            f"👀 Views: {info['views']:,}\n"
            f"📦 Size: {info['size_mb']}MB\n\n"
            "🚀 Uploading to Telegram..."
        )
        
        return True, (file_path, success_msg)
        
    except Exception as e:
        logger.error(f"Error downloading YouTube video: {str(e)}")
        return False, (
            "😓 Oops! Something went wrong while downloading.\n"
            "Please check:\n"
            "• The video URL is valid\n"
            "• The video is public\n"
            "• Try another video\n\n"
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
