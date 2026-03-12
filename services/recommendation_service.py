import os
import logging
import requests
import random
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Cache: (timestamp, [candidates])
_apple_cache: Dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 hour


def _fetch_apple_top_songs() -> List[Dict]:
    """Fetch global Apple Music top 100 with caching."""
    now = time.time()
    cached = _apple_cache.get('global')
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    candidates = []
    try:
        url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json"
        r = requests.get(url, timeout=8, headers={'User-Agent': 'LyricsMasterBot/1.0'})
        if r.status_code == 200:
            results = r.json().get('feed', {}).get('results', [])
            for item in results:
                name = item.get('name', '').strip()
                artist = item.get('artistName', '').strip()
                if name and artist:
                    candidates.append({
                        'name': name,
                        'artist': artist,
                        'reason': 'Trending on Apple Music Top 100',
                    })
            logger.info(f"Apple Music top 100 fetched {len(candidates)} tracks")
    except Exception as e:
        logger.debug(f"Apple Music global chart failed: {e}")

    if candidates:
        _apple_cache['global'] = (now, candidates)
    return candidates


GENRE_RECOMMENDATIONS = {
    'afrobeats': [
        {'artist': 'Ayra Starr', 'name': 'Rush', 'reason': 'Afrobeats/Amapiano crossover energy'},
        {'artist': 'Rema', 'name': 'Calm Down', 'reason': 'Smooth Afrobeats with global appeal'},
        {'artist': 'Burna Boy', 'name': 'Last Last', 'reason': 'Nigerian Afrobeats with emotional depth'},
        {'artist': 'Wizkid', 'name': 'Essence', 'reason': 'Laid-back Afrobeats vibe'},
        {'artist': 'CKay', 'name': 'Love Nwantiti', 'reason': 'Afrobeats love song crossover'},
        {'artist': 'Tiwa Savage', 'name': "Somebody's Son", 'reason': 'Afrobeats with emotional storytelling'},
        {'artist': 'Fireboy DML', 'name': 'Peru', 'reason': 'Upbeat Afrobeats with catchy hooks'},
        {'artist': 'Asake', 'name': 'Sungba', 'reason': 'Fuji-influenced Afrobeats'},
        {'artist': 'Omah Lay', 'name': 'Understand', 'reason': 'Mellow Afrobeats R&B blend'},
        {'artist': 'Davido', 'name': 'Fall', 'reason': 'Classic Afrobeats chart hit'},
        {'artist': 'Tems', 'name': 'Free Mind', 'reason': 'Soulful Afrobeats vocals'},
        {'artist': 'Victony', 'name': 'Soweto', 'reason': 'Amapiano-Afrobeats fusion'},
        {'artist': 'Kizz Daniel', 'name': 'Buga', 'reason': 'Celebration Afrobeats anthem'},
        {'artist': 'Oxlade', 'name': 'Ku Lo Sa', 'reason': 'Romantic Afrobeats texture'},
        {'artist': 'Ayra Starr', 'name': 'Commas', 'reason': 'Fresh Afrobeats from 2024'},
        {'artist': 'Rema', 'name': 'Holiday', 'reason': 'Latest Afrobeats from 2024'},
        {'artist': 'Asake', 'name': 'Lonely at the Top', 'reason': 'Introspective Afrobeats 2023'},
        {'artist': 'Burna Boy', 'name': 'City Boys', 'reason': 'Afrobeats swagger anthem'},
    ],
    'pop': [
        {'artist': 'Dua Lipa', 'name': 'Levitating', 'reason': 'Infectious disco-pop energy'},
        {'artist': 'Harry Styles', 'name': 'As It Was', 'reason': 'Modern pop with retro touch'},
        {'artist': 'Olivia Rodrigo', 'name': 'good 4 u', 'reason': 'High-energy pop-punk attitude'},
        {'artist': 'Miley Cyrus', 'name': 'Flowers', 'reason': 'Empowering pop anthem'},
        {'artist': 'Billie Eilish', 'name': 'Happier Than Ever', 'reason': 'Pop with raw emotion'},
        {'artist': 'Taylor Swift', 'name': 'Anti-Hero', 'reason': 'Introspective mega-pop hit'},
        {'artist': 'Sabrina Carpenter', 'name': 'Espresso', 'reason': 'Breezy 2024 pop hit'},
        {'artist': 'Chappell Roan', 'name': 'Hot to Go!', 'reason': 'Bold pop breakout 2024'},
        {'artist': 'Gracie Abrams', 'name': "That's So True", 'reason': 'Emotional indie-pop 2024'},
        {'artist': 'Charli XCX', 'name': 'Boom Clap', 'reason': 'Electro-pop with swagger'},
        {'artist': 'Doja Cat', 'name': 'Paint The Town Red', 'reason': 'Bold pop-rap crossover'},
        {'artist': 'Olivia Rodrigo', 'name': 'vampire', 'reason': '2023 breakup pop anthem'},
        {'artist': 'Taylor Swift', 'name': 'Cruel Summer', 'reason': 'Synth-pop summer classic'},
        {'artist': 'Harry Styles', 'name': 'Watermelon Sugar', 'reason': 'Carefree summer pop'},
        {'artist': 'Dua Lipa', 'name': 'Houdini', 'reason': 'Dance-pop energy from 2024'},
        {'artist': 'Ariana Grande', 'name': 'yes, and?', 'reason': 'Confident pop-dance return 2024'},
        {'artist': 'Sabrina Carpenter', 'name': 'Please Please Please', 'reason': 'Retro-pop charm 2024'},
        {'artist': 'Billie Eilish', 'name': 'LUNCH', 'reason': 'Alt-pop banger from 2024'},
    ],
    'rnb': [
        {'artist': 'SZA', 'name': 'Snooze', 'reason': 'Dreamy contemporary R&B'},
        {'artist': 'The Weeknd', 'name': 'Die For You', 'reason': 'Cinematic R&B with depth'},
        {'artist': 'Daniel Caesar', 'name': 'Best Part', 'reason': 'Silky romantic R&B'},
        {'artist': 'Brent Faiyaz', 'name': 'WY@', 'reason': 'Moody alternative R&B'},
        {'artist': 'Summer Walker', 'name': 'Playing Games', 'reason': 'Vulnerable R&B storytelling'},
        {'artist': 'Jhené Aiko', 'name': 'Sativa', 'reason': 'Atmospheric R&B vibes'},
        {'artist': 'SZA', 'name': 'Kill Bill', 'reason': 'R&B with dark storytelling'},
        {'artist': 'Chris Brown', 'name': 'Under The Influence', 'reason': 'Smooth R&B groove'},
        {'artist': 'Khalid', 'name': 'Talk', 'reason': 'Youthful alternative R&B'},
        {'artist': 'Lucky Daye', 'name': 'Over', 'reason': 'Neo-soul with lush production'},
        {'artist': 'Victoria Monét', 'name': 'On My Mama', 'reason': 'Funky R&B bop from 2023'},
        {'artist': 'Usher', 'name': 'Good Good', 'reason': 'Classic R&B sound 2024'},
        {'artist': 'SZA', 'name': 'Saturn', 'reason': 'Ethereal R&B from 2024'},
        {'artist': 'The Weeknd', 'name': 'Timeless', 'reason': 'Smooth R&B from 2024'},
        {'artist': 'Tyla', 'name': 'Jump', 'reason': 'Afro-R&B crossover 2024'},
        {'artist': 'H.E.R.', 'name': 'Focus', 'reason': 'Soulful guitar-driven R&B'},
        {'artist': 'Chlöe', 'name': 'Pray It Away', 'reason': 'Powerful contemporary R&B'},
        {'artist': 'Brent Faiyaz', 'name': 'Loose Change', 'reason': 'Introspective modern R&B'},
    ],
    'hiphop': [
        {'artist': 'Kendrick Lamar', 'name': 'HUMBLE.', 'reason': 'Hard-hitting lyrical mastery'},
        {'artist': 'J. Cole', 'name': 'No Role Modelz', 'reason': 'Thoughtful rap storytelling'},
        {'artist': 'Tyler, The Creator', 'name': 'See You Again', 'reason': 'Creative hip-hop artistry'},
        {'artist': 'Travis Scott', 'name': 'SICKO MODE', 'reason': 'Atmospheric trap production'},
        {'artist': 'JID', 'name': 'Surround Sound', 'reason': 'Technical lyricism'},
        {'artist': 'Megan Thee Stallion', 'name': 'Savage', 'reason': 'Confident rap energy'},
        {'artist': '21 Savage', 'name': 'A Lot', 'reason': 'Hard-hitting storytelling'},
        {'artist': 'Drake', 'name': 'Rich Flex', 'reason': 'Chart-dominating rap from 2022'},
        {'artist': 'Kendrick Lamar', 'name': 'Not Like Us', 'reason': '2024 diss track of the year'},
        {'artist': 'Sexyy Red', 'name': 'SkeeYee', 'reason': 'Viral rap anthem from 2023'},
        {'artist': 'GloRilla', 'name': 'FNF', 'reason': 'Memphis rap energy'},
        {'artist': 'Ice Spice', 'name': 'Munch', 'reason': 'Drill-influenced viral rap'},
        {'artist': 'Tyler, The Creator', 'name': 'DOGTOOTH', 'reason': 'Left-field rap from 2024'},
        {'artist': 'Future', 'name': 'Like That', 'reason': 'Trap heat from 2024'},
        {'artist': 'Metro Boomin', 'name': 'Superhero', 'reason': 'Cinematic trap production'},
        {'artist': 'Doechii', 'name': 'Nissan Altima', 'reason': 'Standout rap voice from 2024'},
        {'artist': 'Playboi Carti', 'name': 'Sky', 'reason': 'Atmospheric trap experience'},
        {'artist': 'Lil Wayne', 'name': 'Kat Food', 'reason': 'Veteran rap with fresh delivery'},
    ],
    'rock': [
        {'artist': 'Arctic Monkeys', 'name': 'Do I Wanna Know?', 'reason': 'Dark atmospheric rock'},
        {'artist': 'Foo Fighters', 'name': 'Everlong', 'reason': 'Timeless alternative rock'},
        {'artist': 'Imagine Dragons', 'name': 'Believer', 'reason': 'Anthemic rock energy'},
        {'artist': 'Twenty One Pilots', 'name': 'Stressed Out', 'reason': 'Genre-blending indie rock'},
        {'artist': 'The Killers', 'name': 'Mr. Brightside', 'reason': 'Iconic indie rock anthem'},
        {'artist': 'Muse', 'name': 'Uprising', 'reason': 'Epic stadium rock'},
        {'artist': 'Tame Impala', 'name': 'The Less I Know The Better', 'reason': 'Psychedelic rock groove'},
        {'artist': 'Hozier', 'name': 'Take Me To Church', 'reason': 'Blues-rock with depth'},
        {'artist': 'Paramore', 'name': 'This Is Why', 'reason': 'Post-punk revival 2023'},
        {'artist': 'Wet Leg', 'name': 'Chaise Longue', 'reason': 'Indie rock deadpan wit'},
        {'artist': 'boygenius', 'name': 'Not Strong Enough', 'reason': 'Indie rock supergroup 2023'},
        {'artist': 'Fontaines D.C.', 'name': 'Starburster', 'reason': 'Post-punk 2024 energy'},
        {'artist': 'Coldplay', 'name': 'The Scientist', 'reason': 'Emotional alternative rock'},
        {'artist': 'Radiohead', 'name': 'Creep', 'reason': 'Defining 90s alternative rock'},
        {'artist': 'Linkin Park', 'name': 'The Emptiness Machine', 'reason': 'Rock comeback 2024'},
        {'artist': 'Arctic Monkeys', 'name': 'R U Mine?', 'reason': 'Garage rock energy'},
    ],
    'latin': [
        {'artist': 'Bad Bunny', 'name': 'Titi Me Pregunto', 'reason': 'Latin trap/reggaeton vibes'},
        {'artist': 'Rosalía', 'name': 'DESPECHA', 'reason': 'Spanish pop innovation'},
        {'artist': 'Karol G', 'name': 'BICHOTA', 'reason': 'Reggaeton with attitude'},
        {'artist': 'Rauw Alejandro', 'name': 'Todo de Ti', 'reason': 'Modern Latin pop'},
        {'artist': 'Ozuna', 'name': 'Taki Taki', 'reason': 'Reggaeton dance energy'},
        {'artist': 'Bad Bunny', 'name': 'Monaco', 'reason': 'Latin trap from 2024'},
        {'artist': 'Karol G', 'name': 'Mañana Será Bonito', 'reason': 'Latin pop 2023'},
        {'artist': 'Peso Pluma', 'name': 'Ella Baila Sola', 'reason': 'Regional Mexican breakout 2023'},
        {'artist': 'Shakira', 'name': 'Bzrp Music Sessions #53', 'reason': 'Viral Latin pop 2023'},
        {'artist': 'Myke Towers', 'name': 'La Inocente', 'reason': 'Smooth reggaeton flow'},
        {'artist': 'Feid', 'name': 'Chorrito Pa Las Animas', 'reason': 'Chill reggaeton 2023'},
        {'artist': 'Anitta', 'name': 'Funk Rave', 'reason': 'Brazilian funk crossover'},
        {'artist': 'Rauw Alejandro', 'name': 'Lokera', 'reason': 'Uptempo reggaeton 2022'},
        {'artist': 'J Balvin', 'name': 'Con Altura', 'reason': 'Classic reggaeton crossover'},
    ],
    'classic': [
        {'artist': 'Fleetwood Mac', 'name': 'Dreams', 'reason': 'Timeless classic rock'},
        {'artist': 'The Beatles', 'name': 'Come Together', 'reason': 'Iconic songwriting'},
        {'artist': 'Led Zeppelin', 'name': 'Stairway to Heaven', 'reason': 'Epic classic rock'},
        {'artist': 'Pink Floyd', 'name': 'Comfortably Numb', 'reason': 'Atmospheric masterpiece'},
        {'artist': 'Queen', 'name': 'Somebody to Love', 'reason': 'Powerful vocal showcase'},
        {'artist': 'David Bowie', 'name': 'Heroes', 'reason': 'Glam rock anthem'},
        {'artist': 'Stevie Wonder', 'name': 'Superstition', 'reason': 'Funk-soul classic'},
        {'artist': 'Marvin Gaye', 'name': "Let's Get It On", 'reason': 'Smooth soul masterpiece'},
        {'artist': 'Eagles', 'name': 'Hotel California', 'reason': 'Classic rock storytelling'},
        {'artist': 'Prince', 'name': 'Purple Rain', 'reason': 'Iconic 80s rock ballad'},
        {'artist': 'Michael Jackson', 'name': 'Billie Jean', 'reason': 'Pop-funk perfection'},
        {'artist': 'Elton John', 'name': 'Rocket Man', 'reason': 'Classic piano-pop ballad'},
        {'artist': 'Rolling Stones', 'name': 'Paint It Black', 'reason': 'Psychedelic rock edge'},
    ],
}

ARTIST_GENRE_MAP = {
    'tyla': 'afrobeats', 'ayra starr': 'afrobeats', 'rema': 'afrobeats', 'burna boy': 'afrobeats',
    'wizkid': 'afrobeats', 'davido': 'afrobeats', 'ckay': 'afrobeats', 'fireboy dml': 'afrobeats',
    'tiwa savage': 'afrobeats', 'asake': 'afrobeats', 'omah lay': 'afrobeats', 'tems': 'afrobeats',
    'victony': 'afrobeats', 'kizz daniel': 'afrobeats', 'oxlade': 'afrobeats',
    'taylor swift': 'pop', 'ed sheeran': 'pop', 'dua lipa': 'pop', 'harry styles': 'pop',
    'olivia rodrigo': 'pop', 'billie eilish': 'pop', 'ariana grande': 'pop', 'miley cyrus': 'pop',
    'katy perry': 'pop', 'bruno mars': 'pop', 'justin bieber': 'pop', 'shawn mendes': 'pop',
    'charlie puth': 'pop', 'lizzo': 'pop', 'doja cat': 'pop', 'camila cabello': 'pop',
    'sabrina carpenter': 'pop', 'chappell roan': 'pop', 'gracie abrams': 'pop',
    'sza': 'rnb', 'the weeknd': 'rnb', 'daniel caesar': 'rnb', 'h.e.r.': 'rnb',
    'brent faiyaz': 'rnb', 'summer walker': 'rnb', 'jhene aiko': 'rnb', 'khalid': 'rnb',
    'frank ocean': 'rnb', 'chris brown': 'rnb', 'usher': 'rnb', 'alicia keys': 'rnb',
    'adele': 'rnb', 'sam smith': 'rnb', 'john legend': 'rnb', 'victoria monet': 'rnb',
    'lucky daye': 'rnb', 'chloe': 'rnb',
    'drake': 'hiphop', 'kendrick lamar': 'hiphop', 'j. cole': 'hiphop', 'kanye west': 'hiphop',
    'travis scott': 'hiphop', 'eminem': 'hiphop', 'lil wayne': 'hiphop', 'jay-z': 'hiphop',
    'tyler, the creator': 'hiphop', 'megan thee stallion': 'hiphop', 'nicki minaj': 'hiphop',
    'post malone': 'hiphop', '21 savage': 'hiphop', 'jid': 'hiphop', 'future': 'hiphop',
    'sexyy red': 'hiphop', 'glorilla': 'hiphop', 'ice spice': 'hiphop', 'doechii': 'hiphop',
    'bad bunny': 'latin', 'rosalia': 'latin', 'karol g': 'latin', 'rauw alejandro': 'latin',
    'ozuna': 'latin', 'j balvin': 'latin', 'daddy yankee': 'latin', 'peso pluma': 'latin',
    'shakira': 'latin', 'myke towers': 'latin', 'feid': 'latin', 'anitta': 'latin',
    'queen': 'rock', 'the beatles': 'rock', 'led zeppelin': 'rock', 'pink floyd': 'rock',
    'nirvana': 'rock', 'foo fighters': 'rock', 'arctic monkeys': 'rock',
    'imagine dragons': 'rock', 'coldplay': 'rock', 'u2': 'rock', 'the killers': 'rock',
    'tame impala': 'rock', 'hozier': 'rock', 'paramore': 'rock', 'wet leg': 'rock',
    'boygenius': 'rock', 'radiohead': 'rock', 'muse': 'rock', 'linkin park': 'rock',
    'fleetwood mac': 'classic', 'elvis presley': 'classic', 'michael jackson': 'pop',
    'whitney houston': 'rnb', 'mariah carey': 'rnb', 'rihanna': 'pop',
    'david bowie': 'classic', 'stevie wonder': 'classic', 'marvin gaye': 'classic',
    'eagles': 'classic', 'prince': 'classic', 'elton john': 'classic',
}

MOOD_GENRE_WEIGHTS = {
    'energetic': ['afrobeats', 'pop', 'hiphop', 'rock'],
    'romantic': ['rnb', 'pop', 'latin'],
    'happy': ['pop', 'afrobeats', 'latin'],
    'sad': ['rnb', 'pop', 'rock'],
    'relaxed': ['rnb', 'pop', 'classic'],
}

_ITUNES_GENRE_MAP = {
    'hip-hop/rap': 'hiphop', 'hip hop/rap': 'hiphop', 'hip-hop': 'hiphop',
    'r&b/soul': 'rnb', 'r&b': 'rnb', 'soul': 'rnb',
    'pop': 'pop', 'dance': 'pop', 'electronic': 'pop',
    'rock': 'rock', 'alternative': 'rock', 'indie': 'rock',
    'latin': 'latin', 'reggaeton': 'latin', 'latin urban': 'latin',
    'country': 'pop', 'jazz': 'classic', 'classical': 'classic',
    'k-pop': 'pop', 'afrobeats': 'afrobeats', 'reggae': 'afrobeats',
    'metal': 'rock', 'punk': 'rock', 'blues': 'rnb', 'funk': 'rnb',
}


def _detect_genre(artist: str, song: str, mood: str) -> str:
    artist_lower = artist.lower().strip()
    if artist_lower in ARTIST_GENRE_MAP:
        return ARTIST_GENRE_MAP[artist_lower]

    try:
        search_term = f"{artist} {song}" if song else artist
        r = requests.get(
            'https://itunes.apple.com/search',
            params={'term': search_term, 'media': 'music', 'entity': 'song', 'limit': 1},
            timeout=5
        )
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results:
                itunes_genre = results[0].get('primaryGenreName', '').lower()
                mapped = _ITUNES_GENRE_MAP.get(itunes_genre)
                if mapped:
                    logger.info(f"iTunes genre for '{artist} - {song}': {itunes_genre} -> {mapped}")
                    ARTIST_GENRE_MAP[artist_lower] = mapped
                    return mapped
    except Exception:
        pass

    mood_genres = MOOD_GENRE_WEIGHTS.get(mood, ['pop'])
    return mood_genres[0] if mood_genres else 'pop'


def _get_apple_recommendations(artist: str, song: str) -> Optional[List[Dict]]:
    """Get recommendations from Apple Music global top 100."""
    candidates = _fetch_apple_top_songs()

    if not candidates:
        return None

    # Filter out the source artist and the exact source song
    filtered = [
        c for c in candidates
        if c['artist'].lower() != artist.lower()
        and c['name'].lower() != song.lower()
    ]
    if len(filtered) < 3:
        return None

    # Random sample so results feel fresh on every call
    sample_size = min(5, len(filtered))
    return random.sample(filtered, sample_size)


def _get_curated_recommendations(artist: str, song: str, mood: str) -> List[Dict]:
    genre = _detect_genre(artist, song, mood)
    logger.info(f"Curated recommendations: genre='{genre}' for '{artist} - {song}' (mood={mood})")

    pool = list(GENRE_RECOMMENDATIONS.get(genre, GENRE_RECOMMENDATIONS['pop']))
    filtered = [s for s in pool if s['artist'].lower() != artist.lower()]

    if len(filtered) < 3:
        related_genres = MOOD_GENRE_WEIGHTS.get(mood, ['pop'])
        for rg in related_genres:
            if rg != genre:
                extras = GENRE_RECOMMENDATIONS.get(rg, [])
                for s in extras:
                    if s['artist'].lower() != artist.lower() and s not in filtered:
                        filtered.append(s)
                        if len(filtered) >= 15:
                            break

    return random.sample(filtered, min(5, len(filtered)))


def get_similar_songs(artist: str, song: str, mood: str) -> List[Dict]:
    try:
        apple_recs = _get_apple_recommendations(artist, song)
        if apple_recs and len(apple_recs) >= 3:
            logger.info(f"Using Apple Music recommendations for '{artist} - {song}'")
            return apple_recs

        logger.info(f"Using curated recommendations for '{artist} - {song}'")
        return _get_curated_recommendations(artist, song, mood)

    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return _get_curated_recommendations(artist, song, mood)


def format_recommendations(recommendations: List[Dict], based_on: str = None) -> str:
    if not recommendations:
        return "😕 Sorry, I couldn't find recommendations right now. Try another song!"

    header = "🎵 Songs You Might Love\n"
    if based_on:
        header = f"🎵 If you like \"{based_on}\", try these:\n"

    header += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    lines = []

    for i, song in enumerate(recommendations, 1):
        emoji = ['🔥', '✨', '💫', '🎶', '⭐'][i - 1] if i <= 5 else '🎵'
        line = f"{emoji} {song['artist']} — {song['name']}"

        if song.get('reason'):
            line += f"\n   ↳ {song['reason']}"
        elif song.get('match'):
            line += f" ({song['match']}% match)"

        lines.append(line)

    body = '\n\n'.join(lines)

    footer = (
        "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
        "🎤 /lyrics to see any song's lyrics\n"
        "📊 /analyze for deeper insights"
    )

    return header + body + footer
