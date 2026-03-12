import os
import logging
import requests
import base64
import random
import time
from typing import List, Dict, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

_spotify_token_cache = {'token': None, 'expires': 0}


def _get_spotify_token() -> Optional[str]:
    now = time.time()
    if _spotify_token_cache['token'] and _spotify_token_cache['expires'] > now:
        return _spotify_token_cache['token']

    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not client_id or not client_secret:
        return None

    try:
        auth_base64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        r = requests.post('https://accounts.spotify.com/api/token',
            headers={'Authorization': f'Basic {auth_base64}', 'Content-Type': 'application/x-www-form-urlencoded'},
            data={'grant_type': 'client_credentials'}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            _spotify_token_cache['token'] = data['access_token']
            _spotify_token_cache['expires'] = now + data.get('expires_in', 3600) - 60
            return _spotify_token_cache['token']
    except Exception as e:
        logger.debug(f"Spotify token error: {e}")
    return None


def _get_spotify_recommendations(artist: str, song: str) -> Optional[List[Dict]]:
    token = _get_spotify_token()
    if not token:
        return None

    try:
        headers = {'Authorization': f'Bearer {token}'}
        sr = requests.get('https://api.spotify.com/v1/search',
            headers=headers,
            params={'q': f'track:{song} artist:{artist}', 'type': 'track', 'limit': 1},
            timeout=8)

        if sr.status_code != 200:
            return None

        items = sr.json().get('tracks', {}).get('items', [])
        if not items:
            sr = requests.get('https://api.spotify.com/v1/search',
                headers=headers,
                params={'q': f'{artist} {song}', 'type': 'track', 'limit': 1},
                timeout=8)
            if sr.status_code != 200:
                return None
            items = sr.json().get('tracks', {}).get('items', [])
            if not items:
                return None

        seed_track = items[0]
        track_id = seed_track['id']
        seed_artist_id = seed_track['artists'][0]['id'] if seed_track.get('artists') else None

        rec_params = {'seed_tracks': track_id, 'limit': 20}
        if seed_artist_id:
            rec_params['seed_artists'] = seed_artist_id

        rr = requests.get('https://api.spotify.com/v1/recommendations',
            headers=headers, params=rec_params, timeout=8)
        if rr.status_code != 200:
            return None

        recommendations = []
        seen = set()
        for t in rr.json().get('tracks', []):
            artist_name = t['artists'][0]['name'] if t.get('artists') else 'Unknown'
            track_name = t['name']
            key = f"{artist_name.lower()}-{track_name.lower()}"
            if key in seen or artist_name.lower() == artist.lower():
                continue
            seen.add(key)
            recommendations.append({
                'name': track_name,
                'artist': artist_name,
                'popularity': t.get('popularity', 0)
            })

        if len(recommendations) > 5:
            recommendations = random.sample(recommendations, 5)
        return recommendations if recommendations else None

    except Exception as e:
        logger.debug(f"Spotify recommendations error: {e}")
        return None


def _get_lastfm_recommendations(artist: str, song: str) -> Optional[List[Dict]]:
    api_key = os.environ.get('LASTFM_API_KEY')
    if not api_key:
        return None

    try:
        r = requests.get('https://ws.audioscrobbler.com/2.0/', params={
            'method': 'track.getsimilar', 'artist': artist, 'track': song,
            'api_key': api_key, 'format': 'json', 'limit': 20
        }, timeout=8)

        if r.status_code != 200:
            return None

        tracks = r.json().get('similartracks', {}).get('track', [])
        if not tracks:
            return None

        recommendations = []
        for t in tracks:
            recommendations.append({
                'name': t['name'],
                'artist': t['artist']['name'],
                'match': round(float(t.get('match', 0)) * 100)
            })

        if len(recommendations) > 5:
            recommendations = random.sample(recommendations, 5)
        return recommendations if recommendations else None

    except Exception as e:
        logger.debug(f"Last.fm recommendations error: {e}")
        return None


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
        {'artist': 'H.E.R.', 'name': 'Focus', 'reason': 'Soulful guitar-driven R&B'},
        {'artist': 'Lucky Daye', 'name': 'Over', 'reason': 'Neo-soul with lush production'},
        {'artist': 'Brent Faiyaz', 'name': 'Loose Change', 'reason': 'Introspective modern R&B'},
        {'artist': 'Victoria Monét', 'name': 'On My Mama', 'reason': 'Funky R&B bop from 2023'},
        {'artist': 'Chlöe', 'name': 'Pray It Away', 'reason': 'Powerful contemporary R&B'},
        {'artist': 'Usher', 'name': 'Good Good', 'reason': 'Classic R&B sound 2024'},
        {'artist': 'SZA', 'name': 'Saturn', 'reason': 'Ethereal R&B from 2024'},
        {'artist': 'The Weeknd', 'name': 'Timeless', 'reason': 'Smooth R&B from 2024'},
        {'artist': 'Tyla', 'name': 'Jump', 'reason': 'Afro-R&B crossover 2024'},
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
        {'artist': 'Lil Wayne', 'name': 'Kat Food', 'reason': 'Veteran rap with fresh delivery'},
        {'artist': 'Future', 'name': 'Like That', 'reason': 'Trap heat from 2024'},
        {'artist': 'Metro Boomin', 'name': 'Superhero', 'reason': 'Cinematic trap production'},
        {'artist': 'Playboi Carti', 'name': 'Sky', 'reason': 'Atmospheric trap experience'},
        {'artist': 'Doechii', 'name': 'Nissan Altima', 'reason': 'Standout rap voice from 2024'},
    ],
    'rock': [
        {'artist': 'Arctic Monkeys', 'name': 'Do I Wanna Know?', 'reason': 'Dark atmospheric rock'},
        {'artist': 'Foo Fighters', 'name': 'Everlong', 'reason': 'Timeless alternative rock'},
        {'artist': 'Imagine Dragons', 'name': 'Believer', 'reason': 'Anthemic rock energy'},
        {'artist': 'Twenty One Pilots', 'name': 'Stressed Out', 'reason': 'Genre-blending indie rock'},
        {'artist': 'The Killers', 'name': 'Mr. Brightside', 'reason': 'Iconic indie rock anthem'},
        {'artist': 'Muse', 'name': 'Uprising', 'reason': 'Epic stadium rock'},
        {'artist': 'Tame Impala', 'name': 'The Less I Know The Better', 'reason': 'Psychedelic rock groove'},
        {'artist': 'Arctic Monkeys', 'name': 'R U Mine?', 'reason': 'Garage rock energy'},
        {'artist': 'Hozier', 'name': 'Take Me To Church', 'reason': 'Blues-rock with depth'},
        {'artist': 'Paramore', 'name': 'This Is Why', 'reason': 'Post-punk revival 2023'},
        {'artist': 'Wet Leg', 'name': 'Chaise Longue', 'reason': 'Indie rock deadpan wit'},
        {'artist': 'boygenius', 'name': 'Not Strong Enough', 'reason': 'Indie rock supergroup 2023'},
        {'artist': 'Fontaines D.C.', 'name': 'Starburster', 'reason': 'Post-punk 2024 energy'},
        {'artist': 'Coldplay', 'name': 'The Scientist', 'reason': 'Emotional alternative rock'},
        {'artist': 'Radiohead', 'name': 'Creep', 'reason': 'Defining 90s alternative rock'},
        {'artist': 'Linkin Park', 'name': 'The Emptiness Machine', 'reason': 'Rock comeback 2024'},
    ],
    'latin': [
        {'artist': 'Bad Bunny', 'name': 'Titi Me Pregunto', 'reason': 'Latin trap/reggaeton vibes'},
        {'artist': 'Rosalía', 'name': 'DESPECHA', 'reason': 'Spanish pop innovation'},
        {'artist': 'Karol G', 'name': 'BICHOTA', 'reason': 'Reggaeton with attitude'},
        {'artist': 'Rauw Alejandro', 'name': 'Todo de Ti', 'reason': 'Modern Latin pop'},
        {'artist': 'Ozuna', 'name': 'Taki Taki', 'reason': 'Reggaeton dance energy'},
        {'artist': 'Bad Bunny', 'name': 'un verano sin ti', 'reason': 'Latin experimental 2022'},
        {'artist': 'Karol G', 'name': 'Mañana Será Bonito', 'reason': 'Latin pop 2023'},
        {'artist': 'Peso Pluma', 'name': 'Ella Baila Sola', 'reason': 'Regional Mexican breakout 2023'},
        {'artist': 'Shakira', 'name': 'Bzrp Music Sessions #53', 'reason': 'Viral Latin pop diss 2023'},
        {'artist': 'Bad Bunny', 'name': 'Monaco', 'reason': 'Latin trap from 2024'},
        {'artist': 'Myke Towers', 'name': 'La Inocente', 'reason': 'Smooth reggaeton flow'},
        {'artist': 'Feid', 'name': 'Chorrito Pa Las Animas', 'reason': 'Chill reggaeton 2023'},
        {'artist': 'Anitta', 'name': 'Funk Rave', 'reason': 'Brazilian funk crossover'},
        {'artist': 'Rauw Alejandro', 'name': 'Lokera', 'reason': 'Uptempo reggaeton 2022'},
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
    'tiwa savage': 'afrobeats', 'asake': 'afrobeats', 'omah lay': 'afrobeats',
    'taylor swift': 'pop', 'ed sheeran': 'pop', 'dua lipa': 'pop', 'harry styles': 'pop',
    'olivia rodrigo': 'pop', 'billie eilish': 'pop', 'ariana grande': 'pop', 'miley cyrus': 'pop',
    'katy perry': 'pop', 'bruno mars': 'pop', 'justin bieber': 'pop', 'shawn mendes': 'pop',
    'charlie puth': 'pop', 'lizzo': 'pop', 'doja cat': 'pop', 'camila cabello': 'pop',
    'sza': 'rnb', 'the weeknd': 'rnb', 'daniel caesar': 'rnb', 'h.e.r.': 'rnb',
    'brent faiyaz': 'rnb', 'summer walker': 'rnb', 'jhene aiko': 'rnb', 'khalid': 'rnb',
    'frank ocean': 'rnb', 'chris brown': 'rnb', 'usher': 'rnb', 'alicia keys': 'rnb',
    'adele': 'rnb', 'sam smith': 'rnb', 'john legend': 'rnb',
    'drake': 'hiphop', 'kendrick lamar': 'hiphop', 'j. cole': 'hiphop', 'kanye west': 'hiphop',
    'travis scott': 'hiphop', 'eminem': 'hiphop', 'lil wayne': 'hiphop', 'jay-z': 'hiphop',
    'tyler, the creator': 'hiphop', 'megan thee stallion': 'hiphop', 'nicki minaj': 'hiphop',
    'post malone': 'hiphop', '21 savage': 'hiphop', 'jid': 'hiphop', 'future': 'hiphop',
    'bad bunny': 'latin', 'rosalia': 'latin', 'karol g': 'latin', 'rauw alejandro': 'latin',
    'ozuna': 'latin', 'j balvin': 'latin', 'daddy yankee': 'latin',
    'queen': 'rock', 'the beatles': 'rock', 'led zeppelin': 'rock', 'pink floyd': 'rock',
    'nirvana': 'rock', 'foo fighters': 'rock', 'arctic monkeys': 'rock',
    'imagine dragons': 'rock', 'coldplay': 'rock', 'u2': 'rock', 'the killers': 'rock',
    'fleetwood mac': 'classic', 'elvis presley': 'classic', 'michael jackson': 'pop',
    'whitney houston': 'rnb', 'mariah carey': 'rnb', 'rihanna': 'pop',
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


def _get_curated_recommendations(artist: str, song: str, mood: str) -> List[Dict]:
    genre = _detect_genre(artist, song, mood)
    logger.info(f"Curated recommendations: genre='{genre}' for '{artist} - {song}' (mood={mood})")

    pool = GENRE_RECOMMENDATIONS.get(genre, GENRE_RECOMMENDATIONS['pop'])
    filtered = [s for s in pool if s['artist'].lower() != artist.lower()]

    if len(filtered) < 3:
        related_genres = MOOD_GENRE_WEIGHTS.get(mood, ['pop'])
        for rg in related_genres:
            if rg != genre:
                extras = GENRE_RECOMMENDATIONS.get(rg, [])
                for s in extras:
                    if s['artist'].lower() != artist.lower() and s not in filtered:
                        filtered.append(s)
                        if len(filtered) >= 7:
                            break

    return random.sample(filtered, min(5, len(filtered)))


def get_similar_songs(artist: str, song: str, mood: str) -> List[Dict]:
    try:
        spotify_recs = _get_spotify_recommendations(artist, song)
        if spotify_recs and len(spotify_recs) >= 3:
            logger.info(f"Using Spotify recommendations for '{artist} - {song}'")
            return spotify_recs

        lastfm_recs = _get_lastfm_recommendations(artist, song)
        if lastfm_recs and len(lastfm_recs) >= 3:
            logger.info(f"Using Last.fm recommendations for '{artist} - {song}'")
            return lastfm_recs

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
