import logging
import os
import time
import tempfile
from typing import Optional, Tuple
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

def download_music(artist: str, song: str) -> Optional[Tuple[str, str]]:
    """
    Download a song from YouTube and convert it to MP3.
    Returns a tuple of (file_path, info_message) if successful, None otherwise.
    """
    try:
        # Clean up search terms
        search_query = f"{artist.strip()} - {song.strip()} official audio"
        logger.info(f"Searching for: {search_query}")

        # Create a temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'max_filesize': 50 * 1024 * 1024,  # 50MB limit
            }

            # Search and download
            with YoutubeDL(ydl_opts) as ydl:
                # First, search for video
                result = ydl.extract_info(f"ytsearch1:{search_query}", download=False)

                if not result or 'entries' not in result or not result['entries']:
                    return None

                video = result['entries'][0]
                duration = video.get('duration', 0)

                # Check duration (max 10 minutes)
                if duration > 600:
                    return None

                # Download and convert
                ydl.download([video['webpage_url']])

                # Find the downloaded file
                mp3_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp3')]
                if not mp3_files:
                    return None

                # Move to new location
                original_path = os.path.join(temp_dir, mp3_files[0])
                new_filename = f"{artist}_{song}_{int(time.time())}.mp3".replace(" ", "_")
                new_path = os.path.join(tempfile.gettempdir(), new_filename)

                os.rename(original_path, new_path)

                # Create info message
                info = (
                    f"🎵 Found: {video.get('title', 'Unknown Title')}\n"
                    f"⏱ Duration: {duration // 60}:{duration % 60:02d}\n"
                    "📥 Converting to MP3..."
                )

                return new_path, info

    except Exception as e:
        logger.error(f"Error downloading music: {str(e)}")
        return None

def cleanup_music_file(file_path: str) -> None:
    """Clean up the downloaded music file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {str(e)}")