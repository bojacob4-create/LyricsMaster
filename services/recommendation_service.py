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

        rec_params = {'seed_tracks': track_id, 'limit': 15}
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
            'api_key': api_key, 'format': 'json', 'limit': 15
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
        {'artist': 'Ayra Starr', 'name': 'Rush', 'reason': 'Same Afrobeats/Amapiano energy'},
        {'artist': 'Rema', 'name': 'Calm Down', 'reason': 'Smooth Afrobeats with crossover appeal'},
        {'artist': 'Burna Boy', 'name': 'Last Last', 'reason': 'Nigerian Afrobeats with global reach'},
        {'artist': 'Wizkid', 'name': 'Essence', 'reason': 'Laid-back Afrobeats vibe'},
        {'artist': 'CKay', 'name': 'Love Nwantiti', 'reason': 'Afrobeats love song crossover'},
        {'artist': 'Tiwa Savage', 'name': 'Somebody\'s Son', 'reason': 'Afrobeats with emotional depth'},
        {'artist': 'Fireboy DML', 'name': 'Peru', 'reason': 'Upbeat Afrobeats with catchy hooks'},
    ],
    'pop': [
        {'artist': 'Dua Lipa', 'name': 'Levitating', 'reason': 'Infectious pop energy'},
        {'artist': 'Harry Styles', 'name': 'As It Was', 'reason': 'Modern pop with retro touch'},
        {'artist': 'Olivia Rodrigo', 'name': 'good 4 u', 'reason': 'High-energy pop with attitude'},
        {'artist': 'Miley Cyrus', 'name': 'Flowers', 'reason': 'Empowering pop anthem'},
        {'artist': 'Lizzo', 'name': 'About Damn Time', 'reason': 'Feel-good pop with confidence'},
        {'artist': 'SZA', 'name': 'Kill Bill', 'reason': 'Pop/R&B with storytelling flair'},
        {'artist': 'Billie Eilish', 'name': 'Happier Than Ever', 'reason': 'Pop with raw emotion'},
    ],
    'rnb': [
        {'artist': 'SZA', 'name': 'Snooze', 'reason': 'Dreamy R&B vocals'},
        {'artist': 'The Weeknd', 'name': 'Die For You', 'reason': 'Smooth R&B with depth'},
        {'artist': 'Daniel Caesar', 'name': 'Best Part', 'reason': 'Silky R&B duet energy'},
        {'artist': 'H.E.R.', 'name': 'Best Part', 'reason': 'Soulful contemporary R&B'},
        {'artist': 'Brent Faiyaz', 'name': 'WY@', 'reason': 'Moody alternative R&B'},
        {'artist': 'Summer Walker', 'name': 'Playing Games', 'reason': 'Vulnerable R&B songwriting'},
        {'artist': 'Jhené Aiko', 'name': 'Sativa', 'reason': 'Atmospheric R&B vibes'},
    ],
    'hiphop': [
        {'artist': 'Kendrick Lamar', 'name': 'HUMBLE.', 'reason': 'Hard-hitting lyrical mastery'},
        {'artist': 'J. Cole', 'name': 'No Role Modelz', 'reason': 'Thoughtful rap storytelling'},
        {'artist': 'Tyler, The Creator', 'name': 'See You Again', 'reason': 'Creative hip-hop artistry'},
        {'artist': 'Travis Scott', 'name': 'SICKO MODE', 'reason': 'Atmospheric trap production'},
        {'artist': 'JID', 'name': 'Surround Sound', 'reason': 'Technical rap skill'},
        {'artist': 'Megan Thee Stallion', 'name': 'Savage', 'reason': 'Confident rap energy'},
        {'artist': '21 Savage', 'name': 'A Lot', 'reason': 'Hard-hitting storytelling'},
    ],
    'rock': [
        {'artist': 'Arctic Monkeys', 'name': 'Do I Wanna Know?', 'reason': 'Dark, atmospheric rock'},
        {'artist': 'Foo Fighters', 'name': 'Everlong', 'reason': 'Timeless alternative rock'},
        {'artist': 'Imagine Dragons', 'name': 'Believer', 'reason': 'Anthemic rock energy'},
        {'artist': 'Twenty One Pilots', 'name': 'Stressed Out', 'reason': 'Genre-blending rock'},
        {'artist': 'The Killers', 'name': 'Mr. Brightside', 'reason': 'Iconic indie rock anthem'},
        {'artist': 'Muse', 'name': 'Uprising', 'reason': 'Epic stadium rock'},
    ],
    'latin': [
        {'artist': 'Bad Bunny', 'name': 'Titi Me Pregunto', 'reason': 'Latin trap/reggaeton vibes'},
        {'artist': 'Rosalia', 'name': 'DESPECHA', 'reason': 'Spanish pop innovation'},
        {'artist': 'Karol G', 'name': 'BICHOTA', 'reason': 'Reggaeton with attitude'},
        {'artist': 'Rauw Alejandro', 'name': 'Todo de Ti', 'reason': 'Modern Latin pop'},
        {'artist': 'Ozuna', 'name': 'Taki Taki', 'reason': 'Reggaeton dance energy'},
    ],
    'classic': [
        {'artist': 'Fleetwood Mac', 'name': 'Dreams', 'reason': 'Timeless classic rock'},
        {'artist': 'The Beatles', 'name': 'Come Together', 'reason': 'Iconic songwriting'},
        {'artist': 'Led Zeppelin', 'name': 'Stairway to Heaven', 'reason': 'Epic classic rock'},
        {'artist': 'Pink Floyd', 'name': 'Comfortably Numb', 'reason': 'Atmospheric rock masterpiece'},
        {'artist': 'Queen', 'name': 'Somebody to Love', 'reason': 'Powerful vocal showcase'},
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
