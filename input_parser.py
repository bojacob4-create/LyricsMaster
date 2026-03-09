import re
import logging
from typing import Optional, Tuple, List
from services.lyrics_service import get_song_lyrics

logger = logging.getLogger(__name__)


def clean_input(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'["""\u201c\u201d]', '', raw)
    raw = re.sub(r"['''\u2018\u2019]", "'", raw)
    raw = re.sub(r'\s+', ' ', raw)
    return raw


def parse_song_query(raw_input: str) -> List[Tuple[str, str]]:
    logger.info(f"Parsing raw input: '{raw_input}'")
    cleaned = clean_input(raw_input)

    if not cleaned:
        logger.info("Empty input after cleaning")
        return []

    candidates = []

    if ' - ' in cleaned:
        parts = cleaned.split(' - ', 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        if artist and song:
            logger.info(f"Parsed with ' - ': artist='{artist}', song='{song}'")
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif ' – ' in cleaned:
        parts = cleaned.split(' – ', 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        if artist and song:
            logger.info(f"Parsed with ' – ': artist='{artist}', song='{song}'")
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        if artist and song:
            logger.info(f"Parsed with '-': artist='{artist}', song='{song}'")
            candidates.append((artist, song))
            candidates.append((song, artist))

    if not candidates:
        words = cleaned.split()
        if len(words) >= 2:
            for i in range(1, len(words)):
                part1 = ' '.join(words[:i])
                part2 = ' '.join(words[i:])
                candidates.append((part1, part2))
                candidates.append((part2, part1))
            logger.info(f"Generated {len(candidates)} word-split candidates from '{cleaned}'")

    candidates.append(('', cleaned))

    seen = set()
    unique = []
    for c in candidates:
        key = (c[0].lower(), c[1].lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)

    logger.info(f"Total unique search candidates: {len(unique)}")
    return unique


def search_lyrics_with_fallback(raw_input: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    candidates = parse_song_query(raw_input)

    if not candidates:
        return None, None, None, "empty_input"

    for artist, song in candidates:
        search_artist = artist if artist else song
        search_song = song if artist else ''

        if not search_song:
            logger.info(f"Trying song-only search: '{search_artist}'")
            lyrics = get_song_lyrics(search_artist, '')
            if not lyrics:
                lyrics = get_song_lyrics('', search_artist)
            if lyrics:
                logger.info(f"Found lyrics with song-only search: '{search_artist}'")
                return search_artist, '', lyrics, "song_only"
        else:
            logger.info(f"Trying: artist='{search_artist}', song='{search_song}'")
            lyrics = get_song_lyrics(search_artist, search_song)
            if lyrics:
                logger.info(f"Found lyrics: artist='{search_artist}', song='{search_song}'")
                return search_artist, search_song, lyrics, "found"

    logger.info(f"All search attempts failed for: '{raw_input}'")
    return None, None, None, "not_found"
