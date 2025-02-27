import logging
import os
import time
import tempfile
from typing import Optional, Tuple
from yt_dlp import YoutubeDL
import requests

logger = logging.getLogger(__name__)

def download_music(artist: str, song: str) -> Optional[Tuple[str, str]]:
    """
    Download a song from YouTube and convert it to MP3.

    Args:
        artist (str): Artist name
        song (str): Song title

    Returns:
        Optional[Tuple[str, str]]: Tuple of (file_path, info_message) if successful, None otherwise
    """
    try:
        # Clean up search terms
        search_query = f"{artist.strip()} - {song.strip()} official audio"
        logger.info(f"Searching for: {search_query}")

        # Create a temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Configure yt-dlp options
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
                'extract_flat': False,
                'max_filesize': 50 * 1024 * 1024,  # 50MB limit
            }

            # First, search for the video
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    # Search YouTube
                    result = ydl.extract_info(
                        f"ytsearch1:{search_query}",
                        download=False
                    )

                    if not result or 'entries' not in result or not result['entries']:
                        logger.warning(f"No results found for: {search_query}")
                        return None

                    video_info = result['entries'][0]
                    video_url = video_info['webpage_url']
                    duration = video_info.get('duration', 0)

                    # Check duration (max 10 minutes)
                    if duration > 600:
                        logger.warning(f"Video too long: {duration} seconds")
                        return None, "⚠️ Sorry, this song is too long to download (max 10 minutes)"

                    # Download and convert the audio
                    logger.info(f"Downloading audio from: {video_url}")
                    ydl.download([video_url])

                    # Find the downloaded file
                    files = os.listdir(temp_dir)
                    mp3_files = [f for f in files if f.endswith('.mp3')]

                    if not mp3_files:
                        logger.error("No MP3 file found after download")
                        return None

                    # Move the file to a new location that won't be deleted
                    original_path = os.path.join(temp_dir, mp3_files[0])
                    new_filename = f"{artist}_{song}_{int(time.time())}.mp3".replace(" ", "_")
                    new_path = os.path.join(tempfile.gettempdir(), new_filename)

                    os.rename(original_path, new_path)

                    info_message = (
                        f"🎵 Found: {video_info.get('title', 'Unknown Title')}\n"
                        f"⏱ Duration: {duration // 60}:{duration % 60:02d}\n"
                        "📥 Downloading and converting to MP3..."
                    )

                    return new_path, info_message

                except Exception as e:
                    logger.error(f"Error downloading video: {str(e)}")
                    return None

    except Exception as e:
        logger.error(f"Error in download_music: {str(e)}")
        return None

def cleanup_music_file(file_path: str) -> None:
    """Clean up the downloaded music file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {str(e)}")