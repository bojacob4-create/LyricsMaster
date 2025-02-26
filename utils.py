from typing import List, Dict

def format_lyrics(lyrics: str) -> str:
    """
    Format lyrics for Telegram message.
    
    Args:
        lyrics (str): Raw lyrics text
    
    Returns:
        str: Formatted lyrics
    """
    if not lyrics:
        return "No lyrics available."
    
    # Remove extra blank lines and trim
    formatted = '\n'.join(line for line in lyrics.split('\n') if line.strip())
    
    # Telegram has a message length limit
    if len(formatted) > 4000:
        formatted = formatted[:3997] + "..."
    
    return formatted

def format_top_tracks(tracks: List[Dict]) -> str:
    """
    Format top tracks for Telegram message.

    Args:
        tracks (List[Dict]): List of track information

    Returns:
        str: Formatted track list
    """
    if not tracks:
        return "No tracks available."

    header = "🎵 Last.fm Global Top 10:\n\n"
    formatted_tracks = [
        f"{i+1}. {track['artist']} - {track['name']}"
        for i, track in enumerate(tracks)
    ]

    return header + '\n'.join(formatted_tracks)