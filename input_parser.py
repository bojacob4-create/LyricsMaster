import re
import logging
from typing import Optional, Tuple, List
from services.lyrics_service import get_song_lyrics, search_song_info

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
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif ' – ' in cleaned:
        parts = cleaned.split(' – ', 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        if artist and song:
            candidates.append((artist, song))
            candidates.append((song, artist))

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        if artist and song:
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
    logger.info(f"Search with fallback for: '{raw_input}'")
    cleaned = clean_input(raw_input)

    if not cleaned:
        return None, None, None, "empty_input"

    if ' - ' in cleaned or ' – ' in cleaned:
        sep = ' - ' if ' - ' in cleaned else ' – '
        parts = cleaned.split(sep, 1)
        artist_part = parts[0].strip()
        song_part = parts[1].strip()

        if artist_part and song_part:
            logger.info(f"Trying direct: artist='{artist_part}', song='{song_part}'")
            lyrics = get_song_lyrics(artist_part, song_part)
            if lyrics:
                return artist_part, song_part, lyrics, "direct"

            logger.info(f"Trying swapped: artist='{song_part}', song='{artist_part}'")
            lyrics = get_song_lyrics(song_part, artist_part)
            if lyrics:
                return song_part, artist_part, lyrics, "swapped"

    elif '-' in cleaned and not cleaned.startswith('-'):
        parts = cleaned.split('-', 1)
        artist_part = parts[0].strip()
        song_part = parts[1].strip()
        if artist_part and song_part:
            lyrics = get_song_lyrics(artist_part, song_part)
            if lyrics:
                return artist_part, song_part, lyrics, "direct"
            lyrics = get_song_lyrics(song_part, artist_part)
            if lyrics:
                return song_part, artist_part, lyrics, "swapped"

    result = search_song_info('', cleaned)
    if result:
        found_artist, found_track, lyrics = result
        logger.info(f"Search found: '{found_artist} - {found_track}'")
        return found_artist, found_track, lyrics, "search"

    words = cleaned.split()
    if len(words) >= 2:
        for i in range(1, len(words)):
            part1 = ' '.join(words[:i])
            part2 = ' '.join(words[i:])

            lyrics = get_song_lyrics(part1, part2)
            if lyrics:
                return part1, part2, lyrics, "word_split"

            lyrics = get_song_lyrics(part2, part1)
            if lyrics:
                return part2, part1, lyrics, "word_split_swap"

    logger.info(f"All search attempts failed for: '{raw_input}'")
    return None, None, None, "not_found"
