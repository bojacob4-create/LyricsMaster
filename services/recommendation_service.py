import os
import re
import logging
import random
import requests
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────────────────────────────────────
_apple_cache: Dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 hour


# ──────────────────────────────────────────────────────────────────────────────
# Genre map (artist → genre)
# ──────────────────────────────────────────────────────────────────────────────
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
    'charli xcx': 'pop', 'post malone': 'pop',
    'sza': 'rnb', 'the weeknd': 'rnb', 'daniel caesar': 'rnb', 'h.e.r.': 'rnb',
    'brent faiyaz': 'rnb', 'summer walker': 'rnb', 'jhene aiko': 'rnb', 'khalid': 'rnb',
    'frank ocean': 'rnb', 'chris brown': 'rnb', 'usher': 'rnb', 'alicia keys': 'rnb',
    'adele': 'rnb', 'sam smith': 'rnb', 'john legend': 'rnb', 'victoria monet': 'rnb',
    'lucky daye': 'rnb', 'chloe': 'rnb', 'rihanna': 'rnb',
    'whitney houston': 'rnb', 'mariah carey': 'rnb',
    'drake': 'hiphop', 'kendrick lamar': 'hiphop', 'j. cole': 'hiphop', 'kanye west': 'hiphop',
    'travis scott': 'hiphop', 'eminem': 'hiphop', 'lil wayne': 'hiphop', 'jay-z': 'hiphop',
    'tyler, the creator': 'hiphop', 'megan thee stallion': 'hiphop', 'nicki minaj': 'hiphop',
    '21 savage': 'hiphop', 'jid': 'hiphop', 'future': 'hiphop',
    'sexyy red': 'hiphop', 'glorilla': 'hiphop', 'ice spice': 'hiphop', 'doechii': 'hiphop',
    'metro boomin': 'hiphop', 'playboi carti': 'hiphop',
    'bad bunny': 'latin', 'rosalia': 'latin', 'karol g': 'latin', 'rauw alejandro': 'latin',
    'ozuna': 'latin', 'j balvin': 'latin', 'daddy yankee': 'latin', 'peso pluma': 'latin',
    'shakira': 'latin', 'myke towers': 'latin', 'feid': 'latin', 'anitta': 'latin',
    'queen': 'rock', 'the beatles': 'rock', 'led zeppelin': 'rock', 'pink floyd': 'rock',
    'nirvana': 'rock', 'foo fighters': 'rock', 'arctic monkeys': 'rock',
    'imagine dragons': 'rock', 'coldplay': 'rock', 'u2': 'rock', 'the killers': 'rock',
    'tame impala': 'rock', 'hozier': 'rock', 'paramore': 'rock', 'wet leg': 'rock',
    'boygenius': 'rock', 'radiohead': 'rock', 'muse': 'rock', 'linkin park': 'rock',
    'twenty one pilots': 'rock', 'fontaines d.c.': 'rock',
    'fleetwood mac': 'classic', 'elvis presley': 'classic', 'michael jackson': 'pop',
    'david bowie': 'classic', 'stevie wonder': 'classic', 'marvin gaye': 'classic',
    'eagles': 'classic', 'prince': 'classic', 'elton john': 'classic',
    'rolling stones': 'classic',
}

# iTunes genre → internal genre
_ITUNES_GENRE_MAP = {
    'hip-hop/rap': 'hiphop', 'hip hop/rap': 'hiphop', 'hip-hop': 'hiphop',
    'r&b/soul': 'rnb', 'r&b': 'rnb', 'soul': 'rnb',
    'pop': 'pop', 'dance': 'pop', 'electronic': 'pop',
    'rock': 'rock', 'alternative': 'rock', 'indie': 'rock',
    'latin': 'latin', 'reggaeton': 'latin', 'latin urban': 'latin',
    'country': 'pop', 'jazz': 'classic', 'classical': 'classic',
    'k-pop': 'pop', 'afrobeats': 'afrobeats', 'reggae': 'afrobeats',
    'metal': 'rock', 'punk': 'rock', 'blues': 'rnb', 'funk': 'rnb',
    'afropop': 'afrobeats', 'dancehall': 'afrobeats',
}

# ──────────────────────────────────────────────────────────────────────────────
# Artist profile — vocal type + era (used for scoring only, not displayed)
# ──────────────────────────────────────────────────────────────────────────────
# vocal: 'female' | 'male' | 'group'
# era:   'modern' (2020+) | 'recent' (2015-2019) | 'older' (pre-2015)
ARTIST_PROFILE = {
    'tyla': {'vocal': 'female', 'era': 'modern'},
    'ayra starr': {'vocal': 'female', 'era': 'modern'},
    'rema': {'vocal': 'male', 'era': 'modern'},
    'burna boy': {'vocal': 'male', 'era': 'recent'},
    'wizkid': {'vocal': 'male', 'era': 'recent'},
    'davido': {'vocal': 'male', 'era': 'recent'},
    'ckay': {'vocal': 'male', 'era': 'modern'},
    'fireboy dml': {'vocal': 'male', 'era': 'modern'},
    'tiwa savage': {'vocal': 'female', 'era': 'recent'},
    'asake': {'vocal': 'male', 'era': 'modern'},
    'omah lay': {'vocal': 'male', 'era': 'modern'},
    'tems': {'vocal': 'female', 'era': 'modern'},
    'victony': {'vocal': 'male', 'era': 'modern'},
    'kizz daniel': {'vocal': 'male', 'era': 'recent'},
    'oxlade': {'vocal': 'male', 'era': 'modern'},
    'taylor swift': {'vocal': 'female', 'era': 'recent'},
    'ed sheeran': {'vocal': 'male', 'era': 'recent'},
    'dua lipa': {'vocal': 'female', 'era': 'modern'},
    'harry styles': {'vocal': 'male', 'era': 'modern'},
    'olivia rodrigo': {'vocal': 'female', 'era': 'modern'},
    'billie eilish': {'vocal': 'female', 'era': 'modern'},
    'ariana grande': {'vocal': 'female', 'era': 'recent'},
    'miley cyrus': {'vocal': 'female', 'era': 'recent'},
    'katy perry': {'vocal': 'female', 'era': 'older'},
    'bruno mars': {'vocal': 'male', 'era': 'older'},
    'justin bieber': {'vocal': 'male', 'era': 'recent'},
    'shawn mendes': {'vocal': 'male', 'era': 'recent'},
    'charlie puth': {'vocal': 'male', 'era': 'recent'},
    'lizzo': {'vocal': 'female', 'era': 'recent'},
    'doja cat': {'vocal': 'female', 'era': 'modern'},
    'camila cabello': {'vocal': 'female', 'era': 'recent'},
    'sabrina carpenter': {'vocal': 'female', 'era': 'modern'},
    'chappell roan': {'vocal': 'female', 'era': 'modern'},
    'gracie abrams': {'vocal': 'female', 'era': 'modern'},
    'charli xcx': {'vocal': 'female', 'era': 'recent'},
    'post malone': {'vocal': 'male', 'era': 'recent'},
    'sza': {'vocal': 'female', 'era': 'recent'},
    'the weeknd': {'vocal': 'male', 'era': 'recent'},
    'daniel caesar': {'vocal': 'male', 'era': 'recent'},
    'h.e.r.': {'vocal': 'female', 'era': 'recent'},
    'brent faiyaz': {'vocal': 'male', 'era': 'modern'},
    'summer walker': {'vocal': 'female', 'era': 'modern'},
    'jhene aiko': {'vocal': 'female', 'era': 'recent'},
    'khalid': {'vocal': 'male', 'era': 'recent'},
    'frank ocean': {'vocal': 'male', 'era': 'recent'},
    'chris brown': {'vocal': 'male', 'era': 'older'},
    'usher': {'vocal': 'male', 'era': 'older'},
    'alicia keys': {'vocal': 'female', 'era': 'older'},
    'adele': {'vocal': 'female', 'era': 'recent'},
    'sam smith': {'vocal': 'male', 'era': 'recent'},
    'john legend': {'vocal': 'male', 'era': 'older'},
    'victoria monet': {'vocal': 'female', 'era': 'modern'},
    'lucky daye': {'vocal': 'male', 'era': 'modern'},
    'chloe': {'vocal': 'female', 'era': 'modern'},
    'rihanna': {'vocal': 'female', 'era': 'older'},
    'whitney houston': {'vocal': 'female', 'era': 'older'},
    'mariah carey': {'vocal': 'female', 'era': 'older'},
    'drake': {'vocal': 'male', 'era': 'recent'},
    'kendrick lamar': {'vocal': 'male', 'era': 'older'},
    'j. cole': {'vocal': 'male', 'era': 'older'},
    'kanye west': {'vocal': 'male', 'era': 'older'},
    'travis scott': {'vocal': 'male', 'era': 'recent'},
    'eminem': {'vocal': 'male', 'era': 'older'},
    'lil wayne': {'vocal': 'male', 'era': 'older'},
    'jay-z': {'vocal': 'male', 'era': 'older'},
    'tyler, the creator': {'vocal': 'male', 'era': 'recent'},
    'megan thee stallion': {'vocal': 'female', 'era': 'modern'},
    'nicki minaj': {'vocal': 'female', 'era': 'older'},
    '21 savage': {'vocal': 'male', 'era': 'recent'},
    'jid': {'vocal': 'male', 'era': 'modern'},
    'future': {'vocal': 'male', 'era': 'recent'},
    'sexyy red': {'vocal': 'female', 'era': 'modern'},
    'glorilla': {'vocal': 'female', 'era': 'modern'},
    'ice spice': {'vocal': 'female', 'era': 'modern'},
    'doechii': {'vocal': 'female', 'era': 'modern'},
    'metro boomin': {'vocal': 'male', 'era': 'modern'},
    'playboi carti': {'vocal': 'male', 'era': 'modern'},
    'bad bunny': {'vocal': 'male', 'era': 'modern'},
    'rosalia': {'vocal': 'female', 'era': 'modern'},
    'karol g': {'vocal': 'female', 'era': 'modern'},
    'rauw alejandro': {'vocal': 'male', 'era': 'modern'},
    'ozuna': {'vocal': 'male', 'era': 'recent'},
    'j balvin': {'vocal': 'male', 'era': 'recent'},
    'daddy yankee': {'vocal': 'male', 'era': 'older'},
    'peso pluma': {'vocal': 'male', 'era': 'modern'},
    'shakira': {'vocal': 'female', 'era': 'older'},
    'myke towers': {'vocal': 'male', 'era': 'modern'},
    'feid': {'vocal': 'male', 'era': 'modern'},
    'anitta': {'vocal': 'female', 'era': 'modern'},
    'queen': {'vocal': 'group', 'era': 'older'},
    'the beatles': {'vocal': 'group', 'era': 'older'},
    'led zeppelin': {'vocal': 'group', 'era': 'older'},
    'pink floyd': {'vocal': 'group', 'era': 'older'},
    'nirvana': {'vocal': 'group', 'era': 'older'},
    'foo fighters': {'vocal': 'group', 'era': 'older'},
    'arctic monkeys': {'vocal': 'group', 'era': 'older'},
    'imagine dragons': {'vocal': 'group', 'era': 'recent'},
    'coldplay': {'vocal': 'group', 'era': 'older'},
    'u2': {'vocal': 'group', 'era': 'older'},
    'the killers': {'vocal': 'group', 'era': 'older'},
    'tame impala': {'vocal': 'male', 'era': 'recent'},
    'hozier': {'vocal': 'male', 'era': 'recent'},
    'paramore': {'vocal': 'group', 'era': 'recent'},
    'wet leg': {'vocal': 'group', 'era': 'modern'},
    'boygenius': {'vocal': 'group', 'era': 'modern'},
    'radiohead': {'vocal': 'group', 'era': 'older'},
    'muse': {'vocal': 'group', 'era': 'older'},
    'linkin park': {'vocal': 'group', 'era': 'older'},
    'twenty one pilots': {'vocal': 'group', 'era': 'recent'},
    'fontaines d.c.': {'vocal': 'group', 'era': 'modern'},
    'fleetwood mac': {'vocal': 'group', 'era': 'older'},
    'elvis presley': {'vocal': 'male', 'era': 'older'},
    'michael jackson': {'vocal': 'male', 'era': 'older'},
    'david bowie': {'vocal': 'male', 'era': 'older'},
    'stevie wonder': {'vocal': 'male', 'era': 'older'},
    'marvin gaye': {'vocal': 'male', 'era': 'older'},
    'eagles': {'vocal': 'group', 'era': 'older'},
    'prince': {'vocal': 'male', 'era': 'older'},
    'elton john': {'vocal': 'male', 'era': 'older'},
    'rolling stones': {'vocal': 'group', 'era': 'older'},
}

# ──────────────────────────────────────────────────────────────────────────────
# Mood / tempo lookup tables
# ──────────────────────────────────────────────────────────────────────────────

# Keywords in song title → mood signal
_MOOD_KEYWORDS: Dict[str, set] = {
    'sad': {
        'sad', 'cry', 'crying', 'tears', 'heartbreak', 'sorry', 'goodbye', 'alone',
        'lost', 'missing', 'hurt', 'pain', 'broken', 'leaving', 'dark', 'empty',
        'cold', 'ache', 'aching', 'weep', 'weeping', 'sorrow', 'despair', 'grief',
        'die', 'dying', 'dead', 'death', 'gone', 'never', 'miss', 'suffer',
    },
    'romantic': {
        'love', 'heart', 'forever', 'together', 'yours', 'kiss', 'darling', 'baby',
        'hold', 'adore', 'cherish', 'devoted', 'beloved', 'sweetheart', 'romance',
        'lover', 'desire', 'passion', 'dream', 'dreaming', 'tender', 'gentle',
        'mine', 'need', 'want', 'stay', 'close', 'near', 'soul',
    },
    'energetic': {
        'fire', 'lit', 'run', 'move', 'jump', 'fight', 'rise', 'power', 'beast',
        'boss', 'flex', 'wild', 'crazy', 'rush', 'bang', 'hard', 'loud',
        'grind', 'hustle', 'win', 'king', 'god', 'savage', 'hit', 'hype',
    },
    'happy': {
        'happy', 'joy', 'smile', 'laugh', 'fun', 'good', 'bright', 'sunshine',
        'summer', 'beautiful', 'amazing', 'wonderful', 'celebrate', 'party',
        'dance', 'night', 'light', 'shine', 'glow', 'free', 'high',
    },
    'chill': {
        'chill', 'vibe', 'flow', 'easy', 'smooth', 'mellow', 'soft', 'breeze',
        'ocean', 'wave', 'cloud', 'float', 'drift', 'slow', 'quiet', 'still',
        'peace', 'calm', 'haze', 'cool', 'laid',
    },
}

# Handler moods → internal moods (exact pass-through for matching ones)
_HANDLER_MOOD_MAP = {
    'energetic': 'energetic',
    'happy': 'happy',
    'romantic': 'romantic',
    'sad': 'sad',
    'relaxed': 'chill',
    'melancholic': 'sad',
    'upbeat': 'energetic',
}

# Genre → default mood when nothing else is available
_GENRE_MOOD_DEFAULT = {
    'afrobeats': 'energetic',
    'pop': 'happy',
    'rnb': 'romantic',
    'hiphop': 'energetic',
    'rock': 'energetic',
    'latin': 'energetic',
    'classic': 'chill',
}

# Genre → default tempo bucket
_GENRE_TEMPO_DEFAULT = {
    'afrobeats': 'mid',
    'pop': 'mid',
    'rnb': 'slow',
    'hiphop': 'fast',
    'rock': 'fast',
    'latin': 'fast',
    'classic': 'slow',
}

# Mood compatibility — how well two moods pair (0-100)
_MOOD_COMPAT = {
    ('sad', 'sad'): 100, ('sad', 'romantic'): 50, ('sad', 'chill'): 40,
    ('sad', 'happy'): 10, ('sad', 'energetic'): 5,
    ('romantic', 'romantic'): 100, ('romantic', 'sad'): 50, ('romantic', 'chill'): 60,
    ('romantic', 'happy'): 40, ('romantic', 'energetic'): 15,
    ('happy', 'happy'): 100, ('happy', 'energetic'): 70, ('happy', 'chill'): 40,
    ('happy', 'romantic'): 40, ('happy', 'sad'): 10,
    ('energetic', 'energetic'): 100, ('energetic', 'happy'): 70,
    ('energetic', 'chill'): 20, ('energetic', 'romantic'): 15, ('energetic', 'sad'): 5,
    ('chill', 'chill'): 100, ('chill', 'romantic'): 60, ('chill', 'sad'): 40,
    ('chill', 'happy'): 40, ('chill', 'energetic'): 20,
}

# Curated fallback pool
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

MOOD_GENRE_WEIGHTS = {
    'energetic': ['afrobeats', 'pop', 'hiphop', 'rock'],
    'romantic': ['rnb', 'pop', 'latin'],
    'happy': ['pop', 'afrobeats', 'latin'],
    'sad': ['rnb', 'pop', 'rock'],
    'relaxed': ['rnb', 'pop', 'classic'],
}


# ──────────────────────────────────────────────────────────────────────────────
# Song-level energy inference (title keywords → 'high' | 'mid' | 'low')
# These are conservative — mood is the primary signal; keywords only override
# when a strong title-level signal exists.
# ──────────────────────────────────────────────────────────────────────────────
_ENERGY_HIGH_WORDS: frozenset = frozenset({
    'dance', 'fire', 'wild', 'hype', 'party', 'power', 'loud', 'fast',
    'run', 'rush', 'jump', 'burn', 'rage', 'beast', 'flex', 'lit',
    'bounce', 'banger', 'anthem', 'go', 'turn', 'fuel', 'spark',
    'riot', 'electric', 'charged', 'ignite', 'explode', 'rampage',
})
_ENERGY_LOW_WORDS: frozenset = frozenset({
    'sad', 'cry', 'tears', 'lonely', 'alone', 'miss', 'lost',
    'broken', 'hurt', 'sorry', 'goodbye', 'slow', 'quiet', 'still',
    'calm', 'soft', 'sleep', 'dream', 'rest', 'peace', 'breathe',
    'fade', 'whisper', 'empty', 'cold', 'rain', 'dark', 'hollow',
    'silence', 'sorrow', 'grief', 'mourn', 'ache', 'numb',
})

# ──────────────────────────────────────────────────────────────────────────────
# Song-level production feel inference (style/genre → production bucket)
# Buckets: electronic | acoustic | band | trap | cinematic | minimal | mixed
# ──────────────────────────────────────────────────────────────────────────────
_PROD_FROM_STYLE: Dict[str, str] = {
    'dance_pop': 'electronic',   'synth_pop': 'electronic',
    'dance_electronic': 'electronic', 'festival_edm': 'electronic',
    'house': 'electronic',       'pop_rnb': 'electronic',
    'reggaeton': 'electronic',   'amapiano': 'electronic',
    'acoustic_pop': 'acoustic',  'folk_rock': 'acoustic',
    'country': 'acoustic',
    'cinematic_pop': 'cinematic', 'dream_pop': 'cinematic',
    'trap': 'trap',              'melodic_rap': 'trap',
    'lyrical_rap': 'trap',       'female_rap': 'trap',
    'indie_rock': 'band',        'alt_rock': 'band',
    'anthemic_rock': 'band',     'punk_pop': 'band',
    'psychedelic_rock': 'band',  'classic_rock': 'band',
    'alt_pop': 'mixed',          'emotional_pop': 'minimal',
    'smooth_rnb': 'minimal',     'alt_rnb': 'minimal',
    'emotional_rnb': 'minimal',  'sensual_rnb': 'minimal',
    'soul': 'minimal',
    'afrobeats': 'mixed',        'afro_fusion': 'mixed',
    'latin_pop': 'mixed',        'regional_mexican': 'mixed',
}
_PROD_FROM_GENRE: Dict[str, str] = {
    'hiphop': 'trap',  'rnb': 'minimal',  'pop': 'electronic',
    'afrobeats': 'mixed', 'rock': 'band', 'latin': 'mixed',
    'classic': 'band',
}

# Energy compatibility (symmetric)
_ENERGY_COMPAT: Dict[tuple, float] = {
    ('high', 'high'): 100, ('high', 'mid'): 55, ('high', 'low'): 15,
    ('mid',  'mid'):  100, ('mid',  'low'): 60,
    ('low',  'low'):  100,
}

# Production feel compatibility (symmetric)
_PRODUCTION_COMPAT: Dict[tuple, float] = {
    ('electronic', 'electronic'): 100, ('electronic', 'minimal'): 55,
    ('electronic', 'mixed'): 60,       ('electronic', 'trap'): 28,
    ('electronic', 'cinematic'): 35,   ('electronic', 'acoustic'): 8,
    ('electronic', 'band'): 10,
    ('acoustic', 'acoustic'): 100,     ('acoustic', 'minimal'): 65,
    ('acoustic', 'cinematic'): 60,     ('acoustic', 'band'): 65,
    ('acoustic', 'mixed'): 45,         ('acoustic', 'trap'): 6,
    ('trap', 'trap'): 100,             ('trap', 'mixed'): 58,
    ('trap', 'minimal'): 48,           ('trap', 'band'): 12,
    ('band', 'band'): 100,             ('band', 'acoustic'): 65,
    ('band', 'cinematic'): 55,         ('band', 'minimal'): 35,
    ('band', 'mixed'): 40,
    ('cinematic', 'cinematic'): 100,   ('cinematic', 'minimal'): 70,
    ('cinematic', 'acoustic'): 60,     ('cinematic', 'band'): 55,
    ('cinematic', 'mixed'): 50,        ('cinematic', 'trap'): 8,
    ('minimal', 'minimal'): 100,       ('minimal', 'cinematic'): 70,
    ('minimal', 'acoustic'): 65,       ('minimal', 'mixed'): 58,
    ('minimal', 'trap'): 48,           ('minimal', 'band'): 35,
    ('mixed', 'mixed'): 100,           ('mixed', 'minimal'): 58,
    ('mixed', 'electronic'): 60,       ('mixed', 'trap'): 58,
    ('mixed', 'band'): 40,             ('mixed', 'acoustic'): 45,
    ('mixed', 'cinematic'): 50,
}


# ──────────────────────────────────────────────────────────────────────────────
# Style / subgenre layer
# Artist → style family (more specific than genre, used only for scoring)
# ──────────────────────────────────────────────────────────────────────────────
ARTIST_STYLE = {
    # ── Dance / Disco / Synth Pop ─────────────────────────────────────────────
    'dua lipa': 'dance_pop',
    'ariana grande': 'dance_pop',
    'doja cat': 'dance_pop',
    'charli xcx': 'dance_pop',
    'camila cabello': 'dance_pop',
    'katy perry': 'dance_pop',
    'lizzo': 'dance_pop',
    'cardi b': 'dance_pop',
    'nicki minaj': 'dance_pop',
    'meghan trainor': 'dance_pop',
    'the weeknd': 'synth_pop',
    'sabrina carpenter': 'synth_pop',
    'taylor swift': 'synth_pop',
    'post malone': 'synth_pop',
    'charlie puth': 'synth_pop',
    'shawn mendes': 'acoustic_pop',
    'harry styles': 'acoustic_pop',
    'ed sheeran': 'acoustic_pop',
    'justin bieber': 'acoustic_pop',
    'niall horan': 'acoustic_pop',
    # ── Alt / Emotional Pop ───────────────────────────────────────────────────
    'billie eilish': 'alt_pop',
    'gracie abrams': 'alt_pop',
    'chappell roan': 'alt_pop',
    'olivia rodrigo': 'emotional_pop',
    'miley cyrus': 'emotional_pop',
    'bruno mars': 'pop_rnb',
    'michael jackson': 'pop_rnb',
    'lizzo': 'pop_rnb',
    # ── R&B sub-styles ────────────────────────────────────────────────────────
    'sza': 'alt_rnb',
    'brent faiyaz': 'alt_rnb',
    'frank ocean': 'alt_rnb',
    'summer walker': 'alt_rnb',
    'jhene aiko': 'alt_rnb',
    'chloe': 'alt_rnb',
    'daniel caesar': 'smooth_rnb',
    'khalid': 'smooth_rnb',
    'lucky daye': 'smooth_rnb',
    'john legend': 'smooth_rnb',
    'alicia keys': 'smooth_rnb',
    'victoria monet': 'smooth_rnb',
    'h.e.r.': 'emotional_rnb',
    'adele': 'emotional_rnb',
    'sam smith': 'emotional_rnb',
    'usher': 'sensual_rnb',
    'chris brown': 'sensual_rnb',
    'rihanna': 'pop_rnb',
    'beyonce': 'pop_rnb',
    'whitney houston': 'soul',
    'mariah carey': 'soul',
    'stevie wonder': 'soul',
    'marvin gaye': 'soul',
    'alicia keys': 'soul',
    # ── Afro sub-styles ───────────────────────────────────────────────────────
    'burna boy': 'afrobeats',
    'wizkid': 'afrobeats',
    'davido': 'afrobeats',
    'ckay': 'afrobeats',
    'tiwa savage': 'afrobeats',
    'kizz daniel': 'afrobeats',
    'tyla': 'afro_fusion',
    'tems': 'afro_fusion',
    'omah lay': 'afro_fusion',
    'oxlade': 'afro_fusion',
    'rema': 'afro_fusion',
    'ayra starr': 'afro_fusion',
    'asake': 'amapiano',
    'victony': 'amapiano',
    'fireboy dml': 'amapiano',
    # ── Hip-hop sub-styles ────────────────────────────────────────────────────
    'travis scott': 'trap',
    'future': 'trap',
    'playboi carti': 'trap',
    '21 savage': 'trap',
    'metro boomin': 'trap',
    'lil baby': 'melodic_rap',
    'gunna': 'melodic_rap',
    'don toliver': 'trap',
    'rodwave': 'melodic_rap',
    'central cee': 'melodic_rap',
    'latto': 'female_rap',
    'yeat': 'trap',
    'lil wayne': 'melodic_rap',
    'drake': 'melodic_rap',
    'tyler, the creator': 'melodic_rap',
    'kanye west': 'melodic_rap',
    'kendrick lamar': 'lyrical_rap',
    'j. cole': 'lyrical_rap',
    'jid': 'lyrical_rap',
    'eminem': 'lyrical_rap',
    'jay-z': 'lyrical_rap',
    'megan thee stallion': 'female_rap',
    'sexyy red': 'female_rap',
    'glorilla': 'female_rap',
    'ice spice': 'female_rap',
    'doechii': 'female_rap',
    # ── Latin sub-styles ──────────────────────────────────────────────────────
    'bad bunny': 'reggaeton',
    'karol g': 'reggaeton',
    'rauw alejandro': 'reggaeton',
    'ozuna': 'reggaeton',
    'j balvin': 'reggaeton',
    'daddy yankee': 'reggaeton',
    'feid': 'reggaeton',
    'myke towers': 'reggaeton',
    'peso pluma': 'regional_mexican',
    'shakira': 'latin_pop',
    'anitta': 'latin_pop',
    'rosalia': 'latin_pop',
    # ── Dream pop / Cinematic pop ─────────────────────────────────────────────
    'lana del rey': 'dream_pop',
    'cigarettes after sex': 'dream_pop',
    'beach house': 'dream_pop',
    'the xx': 'dream_pop',
    'mazzy star': 'dream_pop',
    'aurora': 'cinematic_pop',
    'birdy': 'cinematic_pop',
    'lorde': 'cinematic_pop',
    'halsey': 'cinematic_pop',
    'sigrid': 'cinematic_pop',
    'florence + the machine': 'cinematic_pop',
    'mitski': 'cinematic_pop',
    'phoebe bridgers': 'dream_pop',
    'boygenius': 'dream_pop',
    # ── Electronic / EDM ─────────────────────────────────────────────────────
    'calvin harris': 'dance_electronic',
    'david guetta': 'dance_electronic',
    'kygo': 'dance_electronic',
    'the chainsmokers': 'dance_electronic',
    'zedd': 'dance_electronic',
    'dj snake': 'dance_electronic',
    'diplo': 'dance_electronic',
    'major lazer': 'dance_electronic',
    'robin schulz': 'dance_electronic',
    'martin solveig': 'dance_electronic',
    'avicii': 'festival_edm',
    'tiesto': 'festival_edm',
    'marshmello': 'festival_edm',
    'skrillex': 'festival_edm',
    'martin garrix': 'festival_edm',
    'deadmau5': 'festival_edm',
    'swedish house mafia': 'festival_edm',
    'above & beyond': 'festival_edm',
    'illenium': 'festival_edm',
    'alesso': 'festival_edm',
    'disclosure': 'house',
    'fred again': 'house',
    'duke dumont': 'house',
    'fisher': 'house',
    'chris lake': 'house',
    'john summit': 'house',
    'bicep': 'house',
    'caribou': 'house',
    'four tet': 'house',
    # ── Country (explicit style to block cross-genre bleed) ───────────────────
    'luke combs': 'country',
    'morgan wallen': 'country',
    'ella langley': 'country',
    'zach bryan': 'country',
    'lainey wilson': 'country',
    'chris stapleton': 'country',
    'kenny chesney': 'country',
    'toby keith': 'country',
    'blake shelton': 'country',
    'garth brooks': 'country',
    'dolly parton': 'country',
    'kacey musgraves': 'country',
    'tyler hubbard': 'country',
    # ── Rock sub-styles ───────────────────────────────────────────────────────
    'arctic monkeys': 'indie_rock',
    'the killers': 'indie_rock',
    'wet leg': 'indie_rock',
    'boygenius': 'indie_rock',
    'fontaines d.c.': 'indie_rock',
    'radiohead': 'alt_rock',
    'foo fighters': 'alt_rock',
    'linkin park': 'alt_rock',
    'twenty one pilots': 'alt_rock',
    'imagine dragons': 'anthemic_rock',
    'muse': 'anthemic_rock',
    'tame impala': 'psychedelic_rock',
    'hozier': 'folk_rock',
    'paramore': 'punk_pop',
    'coldplay': 'anthemic_rock',
    'nirvana': 'alt_rock',
    'pink floyd': 'classic_rock',
    'led zeppelin': 'classic_rock',
    'the beatles': 'classic_rock',
    'queen': 'classic_rock',
    'fleetwood mac': 'classic_rock',
    'rolling stones': 'classic_rock',
    'david bowie': 'classic_rock',
    'prince': 'classic_rock',
    'elton john': 'classic_rock',
    'eagles': 'classic_rock',
    'u2': 'classic_rock',
}

# Per-song style overrides for well-known tracks where the song style
# differs from the artist's primary style (e.g. The Weeknd has both
# sensual_rnb and synth_pop eras).
# Key: (artist_lowercase, substring_of_song_title_lowercase)
SONG_STYLE_OVERRIDE = {
    ('the weeknd', 'blinding lights'): 'synth_pop',
    ('the weeknd', 'save your tears'): 'synth_pop',
    ('the weeknd', 'starboy'): 'synth_pop',
    ('the weeknd', 'die for you'): 'sensual_rnb',
    ('the weeknd', 'wicked games'): 'alt_rnb',
    ('the weeknd', 'in your eyes'): 'synth_pop',
    ('billie eilish', 'bad guy'): 'alt_pop',
    ('billie eilish', 'happier than ever'): 'emotional_pop',
    ('billie eilish', 'lovely'): 'emotional_pop',
    ('billie eilish', 'ocean eyes'): 'emotional_pop',
    ('billie eilish', 'when the party'): 'alt_pop',
    ('taylor swift', 'anti-hero'): 'synth_pop',
    ('taylor swift', 'shake it off'): 'dance_pop',
    ('taylor swift', 'love story'): 'emotional_pop',
    ('taylor swift', 'all too well'): 'emotional_pop',
    ('taylor swift', 'cruel summer'): 'synth_pop',
    ('rihanna', 'umbrella'): 'pop_rnb',
    ('rihanna', 'we found love'): 'dance_pop',
    ('rihanna', 'diamonds'): 'emotional_pop',
    ('adele', 'hello'): 'emotional_rnb',
    ('adele', 'rolling in the deep'): 'soul',
    ('adele', 'someone like you'): 'emotional_rnb',
    ('adele', 'easy on me'): 'emotional_rnb',
    ('sam smith', 'too good at goodbyes'): 'emotional_rnb',
    ('sam smith', 'stay with me'): 'emotional_rnb',
    ('sam smith', 'unholy'): 'dance_pop',
    ('dua lipa', 'levitating'): 'dance_pop',
    ('dua lipa', 'dont start now'): 'dance_pop',
    ('dua lipa', 'physical'): 'dance_pop',
    ('dua lipa', 'houdini'): 'dance_pop',
    ('dua lipa', 'new rules'): 'dance_pop',
    ('burna boy', 'last last'): 'afrobeats',
    ('burna boy', 'ye'): 'afrobeats',
    ('burna boy', 'city boys'): 'afrobeats',
    ('olivia rodrigo', 'drivers license'): 'emotional_pop',
    ('olivia rodrigo', 'vampire'): 'emotional_pop',
    ('olivia rodrigo', 'good 4 u'): 'punk_pop',
    ('miley cyrus', 'flowers'): 'emotional_pop',
    ('miley cyrus', 'wrecking ball'): 'emotional_pop',
    ('tyla', 'water'): 'afro_fusion',
    ('tyla', 'jump'): 'afro_fusion',
}

# Style compatibility matrix (symmetric, 0-100).
# Missing pairs default to 10 (incompatible).
STYLE_COMPAT: Dict[tuple, float] = {
    # ── Within dance/pop family ───────────────────────────────────────────────
    ('dance_pop', 'dance_pop'): 100,
    ('dance_pop', 'synth_pop'): 72,
    ('dance_pop', 'pop_rnb'): 55,
    ('dance_pop', 'emotional_pop'): 30,
    ('dance_pop', 'alt_pop'): 25,
    ('dance_pop', 'acoustic_pop'): 18,
    ('dance_pop', 'latin_pop'): 50,
    ('dance_pop', 'reggaeton'): 40,
    # ── Synth pop ─────────────────────────────────────────────────────────────
    ('synth_pop', 'synth_pop'): 100,
    ('synth_pop', 'dance_pop'): 72,
    ('synth_pop', 'alt_pop'): 55,
    ('synth_pop', 'emotional_pop'): 40,
    ('synth_pop', 'acoustic_pop'): 18,
    ('synth_pop', 'pop_rnb'): 45,
    # ── Alt pop ───────────────────────────────────────────────────────────────
    ('alt_pop', 'alt_pop'): 100,
    ('alt_pop', 'emotional_pop'): 72,
    ('alt_pop', 'synth_pop'): 55,
    ('alt_pop', 'indie_rock'): 55,
    ('alt_pop', 'acoustic_pop'): 45,
    ('alt_pop', 'punk_pop'): 50,
    ('alt_pop', 'alt_rock'): 40,
    ('alt_pop', 'dance_pop'): 25,
    # ── Emotional pop ─────────────────────────────────────────────────────────
    ('emotional_pop', 'emotional_pop'): 100,
    ('emotional_pop', 'alt_pop'): 72,
    ('emotional_pop', 'emotional_rnb'): 68,
    ('emotional_pop', 'acoustic_pop'): 62,
    ('emotional_pop', 'soul'): 55,
    ('emotional_pop', 'synth_pop'): 40,
    ('emotional_pop', 'dance_pop'): 28,
    # ── Acoustic pop ──────────────────────────────────────────────────────────
    ('acoustic_pop', 'acoustic_pop'): 100,
    ('acoustic_pop', 'emotional_pop'): 62,
    ('acoustic_pop', 'alt_pop'): 45,
    ('acoustic_pop', 'folk_rock'): 58,
    ('acoustic_pop', 'indie_rock'): 40,
    ('acoustic_pop', 'synth_pop'): 18,
    ('acoustic_pop', 'dance_pop'): 18,
    # ── R&B family ────────────────────────────────────────────────────────────
    ('smooth_rnb', 'smooth_rnb'): 100,
    ('smooth_rnb', 'alt_rnb'): 65,
    ('smooth_rnb', 'sensual_rnb'): 70,
    ('smooth_rnb', 'emotional_rnb'): 55,
    ('smooth_rnb', 'pop_rnb'): 65,
    ('smooth_rnb', 'soul'): 62,
    ('alt_rnb', 'alt_rnb'): 100,
    ('alt_rnb', 'smooth_rnb'): 65,
    ('alt_rnb', 'sensual_rnb'): 52,
    ('alt_rnb', 'emotional_rnb'): 62,
    ('alt_rnb', 'melodic_rap'): 42,
    ('alt_rnb', 'alt_pop'): 40,
    ('emotional_rnb', 'emotional_rnb'): 100,
    ('emotional_rnb', 'alt_rnb'): 62,
    ('emotional_rnb', 'smooth_rnb'): 55,
    ('emotional_rnb', 'emotional_pop'): 68,
    ('emotional_rnb', 'soul'): 72,
    ('sensual_rnb', 'sensual_rnb'): 100,
    ('sensual_rnb', 'smooth_rnb'): 70,
    ('sensual_rnb', 'alt_rnb'): 52,
    ('sensual_rnb', 'pop_rnb'): 60,
    ('pop_rnb', 'pop_rnb'): 100,
    ('pop_rnb', 'smooth_rnb'): 65,
    ('pop_rnb', 'sensual_rnb'): 60,
    ('pop_rnb', 'dance_pop'): 55,
    ('pop_rnb', 'emotional_rnb'): 50,
    ('soul', 'soul'): 100,
    ('soul', 'emotional_rnb'): 72,
    ('soul', 'smooth_rnb'): 65,
    ('soul', 'pop_rnb'): 50,
    # ── Afro family ───────────────────────────────────────────────────────────
    ('afrobeats', 'afrobeats'): 100,
    ('afrobeats', 'afro_fusion'): 82,
    ('afrobeats', 'amapiano'): 68,
    ('afro_fusion', 'afro_fusion'): 100,
    ('afro_fusion', 'afrobeats'): 82,
    ('afro_fusion', 'amapiano'): 75,
    ('amapiano', 'amapiano'): 100,
    ('amapiano', 'afro_fusion'): 75,
    ('amapiano', 'afrobeats'): 68,
    # Afro cross-genre mismatches (explicit low scores to block bad drift)
    ('afrobeats', 'trap'): 8,
    ('afrobeats', 'melodic_rap'): 12,
    ('afrobeats', 'lyrical_rap'): 8,
    ('afrobeats', 'reggaeton'): 22,
    ('afro_fusion', 'trap'): 8,
    ('afro_fusion', 'melodic_rap'): 12,
    ('amapiano', 'trap'): 8,
    # ── Hip-hop / rap family ──────────────────────────────────────────────────
    ('trap', 'trap'): 100,
    ('trap', 'melodic_rap'): 55,
    ('trap', 'female_rap'): 60,
    ('trap', 'lyrical_rap'): 38,
    ('melodic_rap', 'melodic_rap'): 100,
    ('melodic_rap', 'trap'): 55,
    ('melodic_rap', 'lyrical_rap'): 48,
    ('melodic_rap', 'pop_rnb'): 42,
    ('melodic_rap', 'smooth_rnb'): 38,
    ('lyrical_rap', 'lyrical_rap'): 100,
    ('lyrical_rap', 'melodic_rap'): 48,
    ('lyrical_rap', 'trap'): 38,
    ('lyrical_rap', 'female_rap'): 45,
    ('female_rap', 'female_rap'): 100,
    ('female_rap', 'trap'): 60,
    ('female_rap', 'melodic_rap'): 45,
    ('female_rap', 'dance_pop'): 30,
    # ── Latin family ──────────────────────────────────────────────────────────
    ('reggaeton', 'reggaeton'): 100,
    ('reggaeton', 'latin_pop'): 65,
    ('reggaeton', 'dance_pop'): 40,
    ('reggaeton', 'regional_mexican'): 35,
    ('latin_pop', 'latin_pop'): 100,
    ('latin_pop', 'reggaeton'): 65,
    ('latin_pop', 'dance_pop'): 45,
    ('regional_mexican', 'regional_mexican'): 100,
    ('regional_mexican', 'latin_pop'): 35,
    # ── Rock family ───────────────────────────────────────────────────────────
    ('indie_rock', 'indie_rock'): 100,
    ('indie_rock', 'alt_rock'): 70,
    ('indie_rock', 'alt_pop'): 55,
    ('indie_rock', 'punk_pop'): 60,
    ('indie_rock', 'psychedelic_rock'): 55,
    ('alt_rock', 'alt_rock'): 100,
    ('alt_rock', 'indie_rock'): 70,
    ('alt_rock', 'anthemic_rock'): 60,
    ('alt_rock', 'punk_pop'): 55,
    ('anthemic_rock', 'anthemic_rock'): 100,
    ('anthemic_rock', 'alt_rock'): 60,
    ('anthemic_rock', 'indie_rock'): 45,
    ('folk_rock', 'folk_rock'): 100,
    ('folk_rock', 'indie_rock'): 55,
    ('folk_rock', 'acoustic_pop'): 58,
    ('folk_rock', 'alt_rock'): 45,
    ('punk_pop', 'punk_pop'): 100,
    ('punk_pop', 'indie_rock'): 60,
    ('punk_pop', 'alt_pop'): 50,
    ('psychedelic_rock', 'psychedelic_rock'): 100,
    ('psychedelic_rock', 'indie_rock'): 60,
    ('classic_rock', 'classic_rock'): 100,
    ('classic_rock', 'alt_rock'): 45,
    ('classic_rock', 'folk_rock'): 40,
    # ── Country family ────────────────────────────────────────────────────────
    ('country', 'country'): 100,
    ('country', 'folk_rock'): 40,
    ('country', 'acoustic_pop'): 30,
    # ── Explicit cross-genre blocks ───────────────────────────────────────────
    ('dance_pop', 'classic_rock'): 5,
    ('dance_pop', 'trap'): 10,
    ('dance_pop', 'country'): 5,
    ('synth_pop', 'trap'): 8,
    ('synth_pop', 'country'): 5,
    ('emotional_pop', 'trap'): 8,
    ('emotional_pop', 'country'): 12,
    ('emotional_rnb', 'trap'): 12,
    ('emotional_rnb', 'country'): 8,
    ('alt_pop', 'trap'): 8,
    ('alt_pop', 'country'): 8,
    ('acoustic_pop', 'trap'): 5,
    ('acoustic_pop', 'country'): 30,
    ('smooth_rnb', 'trap'): 12,
    ('smooth_rnb', 'country'): 5,
    ('pop_rnb', 'country'): 5,
    ('afrobeats', 'country'): 3,
    ('afro_fusion', 'country'): 3,
    ('dance_pop', 'regional_mexican'): 8,
    ('emotional_rnb', 'reggaeton'): 15,
    # ── Dream pop family ──────────────────────────────────────────────────────
    ('dream_pop', 'dream_pop'): 100,
    ('dream_pop', 'cinematic_pop'): 88,
    ('dream_pop', 'alt_pop'): 72,
    ('dream_pop', 'emotional_pop'): 65,
    ('dream_pop', 'indie_rock'): 68,
    ('dream_pop', 'psychedelic_rock'): 62,
    ('dream_pop', 'folk_rock'): 58,
    ('dream_pop', 'acoustic_pop'): 45,
    ('dream_pop', 'synth_pop'): 38,
    # Low / block for dream_pop vs R&B and hip-hop
    ('dream_pop', 'alt_rnb'): 15,
    ('dream_pop', 'smooth_rnb'): 8,
    ('dream_pop', 'sensual_rnb'): 5,
    ('dream_pop', 'emotional_rnb'): 20,
    ('dream_pop', 'trap'): 5,
    ('dream_pop', 'melodic_rap'): 8,
    ('dream_pop', 'dance_pop'): 18,
    ('dream_pop', 'dance_electronic'): 12,
    # ── Cinematic pop family ──────────────────────────────────────────────────
    ('cinematic_pop', 'cinematic_pop'): 100,
    ('cinematic_pop', 'dream_pop'): 88,
    ('cinematic_pop', 'alt_pop'): 72,
    ('cinematic_pop', 'emotional_pop'): 68,
    ('cinematic_pop', 'indie_rock'): 68,
    ('cinematic_pop', 'folk_rock'): 62,
    ('cinematic_pop', 'psychedelic_rock'): 55,
    ('cinematic_pop', 'acoustic_pop'): 50,
    ('cinematic_pop', 'synth_pop'): 35,
    # Block R&B / hip-hop bleed
    ('cinematic_pop', 'alt_rnb'): 12,
    ('cinematic_pop', 'smooth_rnb'): 8,
    ('cinematic_pop', 'sensual_rnb'): 5,
    ('cinematic_pop', 'emotional_rnb'): 22,
    ('cinematic_pop', 'trap'): 5,
    ('cinematic_pop', 'dance_pop'): 20,
    ('cinematic_pop', 'dance_electronic'): 10,
    # ── Dance electronic family ───────────────────────────────────────────────
    ('dance_electronic', 'dance_electronic'): 100,
    ('dance_electronic', 'festival_edm'): 80,
    ('dance_electronic', 'house'): 72,
    ('dance_electronic', 'dance_pop'): 75,
    ('dance_electronic', 'synth_pop'): 62,
    ('dance_electronic', 'pop_rnb'): 35,
    # Block incompatible styles
    ('dance_electronic', 'country'): 5,
    ('dance_electronic', 'trap'): 12,
    ('dance_electronic', 'melodic_rap'): 12,
    ('dance_electronic', 'lyrical_rap'): 8,
    ('dance_electronic', 'afrobeats'): 15,
    ('dance_electronic', 'dream_pop'): 12,
    ('dance_electronic', 'cinematic_pop'): 10,
    ('dance_electronic', 'emotional_rnb'): 10,
    # ── Festival EDM family ───────────────────────────────────────────────────
    ('festival_edm', 'festival_edm'): 100,
    ('festival_edm', 'dance_electronic'): 80,
    ('festival_edm', 'house'): 70,
    ('festival_edm', 'synth_pop'): 58,
    ('festival_edm', 'dance_pop'): 60,
    ('festival_edm', 'country'): 5,
    ('festival_edm', 'trap'): 12,
    ('festival_edm', 'dream_pop'): 8,
    # ── House family ──────────────────────────────────────────────────────────
    ('house', 'house'): 100,
    ('house', 'dance_electronic'): 72,
    ('house', 'festival_edm'): 70,
    ('house', 'dance_pop'): 65,
    ('house', 'synth_pop'): 55,
    ('house', 'pop_rnb'): 40,
    ('house', 'country'): 5,
    ('house', 'trap'): 10,
    ('house', 'dream_pop'): 15,
}


# Maps each style to the curated genre pool that contains the best candidates.
# Used to cross-search the right pool even when detected genre differs.
STYLE_GENRE_AFFINITY: Dict[str, str] = {
    'dance_pop': 'pop',   'synth_pop': 'pop',   'alt_pop': 'pop',
    'emotional_pop': 'pop', 'acoustic_pop': 'pop', 'pop_rnb': 'rnb',
    'alt_rnb': 'rnb',     'smooth_rnb': 'rnb',  'emotional_rnb': 'rnb',
    'sensual_rnb': 'rnb', 'soul': 'rnb',
    'afrobeats': 'afrobeats', 'afro_fusion': 'afrobeats', 'amapiano': 'afrobeats',
    'trap': 'hiphop',     'melodic_rap': 'hiphop', 'lyrical_rap': 'hiphop',
    'female_rap': 'hiphop',
    'reggaeton': 'latin', 'latin_pop': 'latin', 'regional_mexican': 'latin',
    'indie_rock': 'rock', 'alt_rock': 'rock',   'anthemic_rock': 'rock',
    'folk_rock': 'rock',  'punk_pop': 'rock',   'psychedelic_rock': 'rock',
    'classic_rock': 'classic',
    # New style families → best curated pool to cross-search
    'dream_pop': 'rock',        # Hozier, Tame Impala, Radiohead in rock pool
    'cinematic_pop': 'rock',    # same — indie/alt artists closest match
    'dance_electronic': 'pop',  # dance_pop artists in pop pool are closest
    'festival_edm': 'pop',      # same
    'house': 'pop',             # same
}


def _get_song_style(artist: str, song: str) -> str:
    """
    Return style/subgenre for a specific song.
    Priority: SONG_STYLE_OVERRIDE → ARTIST_STYLE → 'unknown'
    No external calls; O(1) lookup.
    """
    a_key = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s.*', '', artist.lower().strip(),
                   flags=re.IGNORECASE).strip()
    s_key = song.lower().strip()

    # Check song-level override first
    for (a_frag, s_frag), style in SONG_STYLE_OVERRIDE.items():
        if a_frag in a_key and s_frag in s_key:
            return style

    # Fall back to artist-level style
    if a_key in ARTIST_STYLE:
        return ARTIST_STYLE[a_key]
    for k, v in ARTIST_STYLE.items():
        if k in a_key:
            return v

    return 'unknown'


def _style_compat(s1: str, s2: str) -> float:
    """
    Style compatibility score 0-100 (symmetric).
    Exact match → 100. Unknown on either side → neutral 45.
    Not in STYLE_COMPAT → 10 (incompatible by default).
    """
    if s1 == 'unknown' or s2 == 'unknown':
        return 45.0
    if s1 == s2:
        return 100.0
    score = STYLE_COMPAT.get((s1, s2)) or STYLE_COMPAT.get((s2, s1))
    return float(score) if score is not None else 10.0


def _infer_energy(title: str, mood: str, genre: str) -> str:
    """
    Infer song energy level ('high' | 'mid' | 'low') from the song title.
    Mood is the authoritative fallback; title keywords only override when
    a clear signal is present.
    """
    words = set(re.sub(r"[^a-z\s]", '', title.lower()).split())
    high_hits = len(_ENERGY_HIGH_WORDS & words)
    low_hits  = len(_ENERGY_LOW_WORDS  & words)

    if high_hits > low_hits:
        return 'high'
    if low_hits > high_hits:
        return 'low'

    if mood == 'energetic':
        return 'high'
    if mood in ('sad', 'chill', 'relaxed'):
        return 'low'
    if mood == 'happy':
        return 'high' if genre in ('hiphop', 'rock', 'afrobeats') else 'mid'
    if mood == 'romantic':
        return 'low'
    return 'mid'


def _infer_production(style: str, genre: str) -> str:
    """
    Infer song production feel from its style/subgenre.

    When style is known, look it up in _PROD_FROM_STYLE for a precise value.
    When style is unknown, return 'mixed' — production cannot be reliably
    inferred from genre alone (pop can be trap, acoustic, electronic, etc.).
    Using genre as a fallback when style is unknown creates false matches
    (e.g. an unknown-style song in 'pop' would wrongly score as 'electronic').

    Returns one of: electronic | acoustic | band | trap | cinematic | minimal | mixed
    """
    if style and style != 'unknown':
        prod = _PROD_FROM_STYLE.get(style)
        if prod:
            return prod
    return 'mixed'


def _energy_compat(e1: str, e2: str) -> float:
    """Energy level compatibility score 0-100 (symmetric)."""
    if not e1 or not e2:
        return 50.0
    if e1 == e2:
        return 100.0
    return float(_ENERGY_COMPAT.get((e1, e2)) or _ENERGY_COMPAT.get((e2, e1)) or 30.0)


def _production_compat(p1: str, p2: str) -> float:
    """Production feel compatibility score 0-100 (symmetric)."""
    if not p1 or not p2:
        return 50.0
    if p1 == p2:
        return 100.0
    return float(_PRODUCTION_COMPAT.get((p1, p2)) or _PRODUCTION_COMPAT.get((p2, p1)) or 20.0)


# ──────────────────────────────────────────────────────────────────────────────
# Lightweight metadata helpers (no external API calls)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_genre_fast(artist: str) -> str:
    """Genre from artist map only — no external calls, O(1)."""
    key = artist.lower().strip()
    if key in ARTIST_GENRE_MAP:
        return ARTIST_GENRE_MAP[key]
    # Try stripping 'feat.' suffix
    clean = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s.*', '', key, flags=re.IGNORECASE).strip()
    if clean in ARTIST_GENRE_MAP:
        return ARTIST_GENRE_MAP[clean]
    # Partial match
    for k, v in ARTIST_GENRE_MAP.items():
        if k in key:
            return v
    return 'pop'


def _get_artist_profile(artist: str) -> Dict:
    """Lookup vocal type + era for a known artist; returns safe defaults."""
    key = artist.lower().strip()
    if key in ARTIST_PROFILE:
        return ARTIST_PROFILE[key]
    clean = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s.*', '', key, flags=re.IGNORECASE).strip()
    if clean in ARTIST_PROFILE:
        return ARTIST_PROFILE[clean]
    # Partial
    for k, v in ARTIST_PROFILE.items():
        if k in key:
            return v
    return {'vocal': 'male', 'era': 'modern'}


def _infer_mood_from_title(title: str, genre: str, handler_mood: str) -> str:
    """
    Infer mood priority:
      1. handler_mood (from lyrics analysis) if it maps cleanly
      2. title keyword scan
      3. genre default
    """
    if handler_mood:
        mapped = _HANDLER_MOOD_MAP.get(handler_mood.lower())
        if mapped:
            return mapped

    title_words = set(re.sub(r"[^a-z\s]", '', title.lower()).split())
    best_mood, best_score = None, 0
    for mood, keywords in _MOOD_KEYWORDS.items():
        score = len(keywords & title_words)
        if score > best_score:
            best_score, best_mood = score, mood

    if best_mood and best_score > 0:
        return best_mood

    return _GENRE_MOOD_DEFAULT.get(genre, 'happy')


def _infer_tempo(mood: str, genre: str) -> str:
    """Infer tempo bucket from mood + genre."""
    base = _GENRE_TEMPO_DEFAULT.get(genre, 'mid')
    if mood == 'sad' and genre in ('rnb', 'pop', 'classic'):
        return 'slow'
    if mood == 'energetic' and genre in ('hiphop', 'rock'):
        return 'fast'
    if mood == 'chill':
        return 'slow'
    return base


def _build_song_profile(artist: str, song: str, handler_mood: str, genre: str) -> Dict:
    """
    Build a song-first profile dict.

    Primary signals (derived from the song itself):
      mood       — from title keywords + handler hint
      energy     — from title keywords, with mood as fallback
      production — from style/subgenre mapping
      style      — from SONG_STYLE_OVERRIDE → ARTIST_STYLE (weak hint)

    Secondary signals (artist-level, kept as weak context):
      vocal, era — from ARTIST_PROFILE
    """
    ap    = _get_artist_profile(artist)
    mood  = _infer_mood_from_title(song, genre, handler_mood)
    style = _get_song_style(artist, song)

    energy     = _infer_energy(song, mood, genre)
    production = _infer_production(style, genre)

    return {
        'genre':      genre,
        'mood':       mood,
        'style':      style,
        'energy':     energy,
        'production': production,
        'vocal':      ap.get('vocal', 'male'),
        'era':        ap.get('era', 'modern'),
    }


def _mood_compat(m1: str, m2: str) -> float:
    """Return compatibility score 0-100 between two moods (symmetric)."""
    return float(_MOOD_COMPAT.get((m1, m2)) or _MOOD_COMPAT.get((m2, m1)) or 20)


def _score_candidate(candidate_artist: str, candidate_name: str,
                     candidate_genre: str, source: Dict) -> float:
    """
    Score a candidate against the source song profile (0-100, weighted).

    Weights (v3 — song-first architecture):
      22% mood            primary emotional tone of the song
      20% style           subgenre family; ARTIST_STYLE is a weak hint here
      18% energy          high/mid/low level inferred from the song itself
      15% production      electronic/acoustic/band/trap/cinematic/minimal/mixed
      15% genre           broad pool match
       6% vocal           artist-level signal, kept as weak tiebreaker
       4% era             artist-level signal, kept as weak tiebreaker

    The song-level signals (mood + energy + production = 55%) now outweigh
    artist-level/lookup signals (style + genre + vocal + era = 45%).
    ARTIST_STYLE's contribution is further diluted because style is one
    of seven signals, not the dominant one.
    """
    cp      = _get_artist_profile(candidate_artist)
    c_mood  = _infer_mood_from_title(candidate_name, candidate_genre, '')
    c_style = _get_song_style(candidate_artist, candidate_name)

    c_energy     = _infer_energy(candidate_name, c_mood, candidate_genre)
    c_production = _infer_production(c_style, candidate_genre)

    mood_score       = _mood_compat(c_mood, source['mood'])
    style_score      = _style_compat(c_style, source.get('style', 'unknown'))
    energy_score     = _energy_compat(c_energy, source.get('energy', 'mid'))
    production_score = _production_compat(c_production, source.get('production', 'mixed'))
    genre_score      = 100.0 if candidate_genre == source['genre'] else 20.0
    vocal_score      = 100.0 if cp.get('vocal') == source['vocal'] else 40.0
    era_score        = 100.0 if cp.get('era')   == source['era']   else 30.0

    return (
        0.22 * mood_score       +
        0.20 * style_score      +
        0.18 * energy_score     +
        0.15 * production_score +
        0.15 * genre_score      +
        0.06 * vocal_score      +
        0.04 * era_score
    )


def _generate_reason(candidate_artist: str, candidate_name: str,
                     candidate_genre: str, source: Dict,
                     existing_reason: str = '') -> str:
    """
    Generate a short vibe-based reason string.
    Uses the curated reason when it's already meaningful.
    Generates a new one for Apple Music candidates.
    """
    if existing_reason and existing_reason != 'Trending on Apple Music Top 100':
        return existing_reason

    cp = _get_artist_profile(candidate_artist)
    c_mood = _infer_mood_from_title(candidate_name, candidate_genre, '')

    mood_words = {
        'sad': 'emotional', 'romantic': 'romantic', 'energetic': 'energetic',
        'happy': 'upbeat', 'chill': 'chill',
    }
    genre_words = {
        'afrobeats': 'Afrobeats vibe', 'pop': 'pop sound', 'rnb': 'R&B feel',
        'hiphop': 'hip-hop energy', 'rock': 'rock energy', 'latin': 'Latin groove',
        'classic': 'classic sound',
    }
    vocal_words = {
        'female': 'female vocalist', 'male': 'male vocalist', 'group': 'band/group',
    }

    mood_w = mood_words.get(c_mood, '')
    genre_w = genre_words.get(candidate_genre, 'similar vibe')
    vocal_w = vocal_words.get(cp.get('vocal', ''), '')

    # Genre + mood match → best reason
    if candidate_genre == source['genre'] and c_mood == source['mood']:
        return f"same {mood_w} {genre_w}" if mood_w else genre_w
    if candidate_genre == source['genre']:
        return f"{mood_w} {genre_w}".strip() if mood_w else genre_w
    if c_mood == source['mood']:
        return f"{mood_w} {vocal_w}".strip() if vocal_w else f"{mood_w} {genre_w}".strip()
    return genre_w or 'similar vibe'


# ──────────────────────────────────────────────────────────────────────────────
# Genre detection with iTunes fallback (used for source song only)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_genre(artist: str, song: str, mood: str) -> str:
    """Detect genre: artist map → iTunes API → mood fallback."""
    result = _detect_genre_fast(artist)
    if result != 'pop' or artist.lower().strip() in ARTIST_GENRE_MAP:
        return result

    try:
        r = requests.get(
            'https://itunes.apple.com/search',
            params={'term': f"{artist} {song}", 'media': 'music', 'entity': 'song', 'limit': 1},
            timeout=5,
        )
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results:
                itunes_genre = results[0].get('primaryGenreName', '').lower()
                mapped = _ITUNES_GENRE_MAP.get(itunes_genre)
                if mapped:
                    logger.info(f"iTunes genre: '{artist} - {song}' → {itunes_genre} → {mapped}")
                    ARTIST_GENRE_MAP[artist.lower().strip()] = mapped
                    return mapped
    except Exception:
        pass

    mood_genres = MOOD_GENRE_WEIGHTS.get(mood, ['pop'])
    return mood_genres[0] if mood_genres else 'pop'


# ──────────────────────────────────────────────────────────────────────────────
# Apple Music top 100
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_apple_top_songs() -> List[Dict]:
    """Fetch global Apple Music top 100 with 1-hour caching."""
    now = time.time()
    cached = _apple_cache.get('global')
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    candidates = []
    try:
        url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json"
        r = requests.get(url, timeout=8, headers={'User-Agent': 'LyricsMasterBot/1.0'})
        if r.status_code == 200:
            for item in r.json().get('feed', {}).get('results', []):
                name = item.get('name', '').strip()
                artist = item.get('artistName', '').strip()
                if name and artist:
                    candidates.append({'name': name, 'artist': artist,
                                       'reason': 'Trending on Apple Music Top 100'})
            logger.info(f"Apple Music top 100: {len(candidates)} tracks")
    except Exception as e:
        logger.debug(f"Apple Music chart failed: {e}")

    if candidates:
        _apple_cache['global'] = (now, candidates)
    return candidates


_APPLE_MIN_QUALITY = 76.0  # Minimum average score for top-5 Apple picks to beat curated


def _get_apple_recommendations(artist: str, song: str,
                                source_profile: Dict) -> Optional[List[Dict]]:
    """
    Score + rank Apple Music top 100 by vibe similarity.

    Only returns results when the top picks genuinely match the source profile
    (average score >= _APPLE_MIN_QUALITY). This prevents low-relevance Apple
    Music charts from overriding the more on-point curated pool.
    """
    candidates = _fetch_apple_top_songs()
    if not candidates:
        return None

    filtered = [
        c for c in candidates
        if c['artist'].lower() != artist.lower() and c['name'].lower() != song.lower()
    ]
    if len(filtered) < 3:
        return None

    # Score every candidate (fast: all from lookup tables, no API calls)
    scored = []
    for c in filtered:
        c_genre = _detect_genre_fast(c['artist'])
        score = _score_candidate(c['artist'], c['name'], c_genre, source_profile)
        scored.append((score, c, c_genre))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Quality gate: each candidate must individually exceed the threshold.
    # Songs below the threshold are dropped from the pool entirely — this
    # prevents a low-scoring outlier from being jittered into the final 5
    # (jitter operates on the pool, so a song rated #8 pre-jitter can become
    # #5 post-jitter if its ±2 jitter lands above position 5 scores).
    quality_pool = [(s, c, g) for s, c, g in scored if s >= _APPLE_MIN_QUALITY]
    logger.info(f"[REC] Apple quality pool: {len(quality_pool)} songs >= {_APPLE_MIN_QUALITY} "
                f"for '{artist} - {song}'")

    if len(quality_pool) < 3:
        # Not enough individually-matching songs — curated will be more accurate
        logger.info(f"[REC] Apple quality pool too small, falling back to curated")
        return None

    # Good quality: take top 12 from the quality pool, apply small jitter,
    # then deduplicate by artist.
    top_pool = quality_pool[:12]
    jittered = [(s + random.uniform(-2, 2), c, g) for s, c, g in top_pool]
    jittered.sort(key=lambda x: x[0], reverse=True)

    # Per-artist deduplication: no artist more than once in final 5
    result = []
    seen_artists: set = set()
    for _, c, c_genre in jittered:
        ak = c['artist'].lower()
        if ak not in seen_artists:
            seen_artists.add(ak)
            rec = dict(c)
            rec['reason'] = _generate_reason(
                c['artist'], c['name'], c_genre, source_profile, c.get('reason', '')
            )
            result.append(rec)
        if len(result) == 5:
            break

    # Safety pad: if fewer than 5 unique artists, pull from the broader scored
    # list (not just the quality pool). Check seen_artists — never song-dict
    # equality, because result entries have a modified 'reason' field.
    if len(result) < 5:
        for _, c, c_genre in scored:
            ak = c['artist'].lower()
            if ak not in seen_artists:
                seen_artists.add(ak)
                rec = dict(c)
                rec['reason'] = _generate_reason(
                    c['artist'], c['name'], c_genre, source_profile, c.get('reason', '')
                )
                result.append(rec)
            if len(result) == 5:
                break

    return result


def _get_curated_recommendations(artist: str, song: str,
                                  mood: str, source_profile: Dict) -> List[Dict]:
    """Score + rank curated genre pool by vibe similarity."""
    genre = source_profile['genre']
    source_style = source_profile.get('style', 'unknown')
    logger.info(f"Curated recs: genre='{genre}' style='{source_style}' "
                f"mood='{source_profile['mood']}' for '{artist} - {song}'")

    pool_genres: set = {genre}

    # If the song's style belongs to a different curated pool, include that pool
    # too (e.g. The Weeknd "Blinding Lights" = synth_pop → add pop pool).
    style_genre = STYLE_GENRE_AFFINITY.get(source_style)
    if style_genre and style_genre != genre:
        pool_genres.add(style_genre)
        logger.info(f"[REC] style '{source_style}' pulls in extra pool: '{style_genre}'")

    # Expand with mood-related genres only when the style is unknown.
    # Known styles already route to the correct pool via STYLE_GENRE_AFFINITY;
    # mood expansion would add unrelated genre pools (e.g. rnb into dream_pop queries).
    if source_style == 'unknown':
        for rg in MOOD_GENRE_WEIGHTS.get(mood, ['pop']):
            if rg not in pool_genres:
                pool_genres.add(rg)
                if len(pool_genres) >= 3:
                    break

    # Build flat candidate list (candidate_dict, pool_genre)
    pool: List[tuple] = []
    seen_keys: set = set()
    for pg in pool_genres:
        for entry in GENRE_RECOMMENDATIONS.get(pg, []):
            key = (entry['artist'].lower(), entry['name'].lower())
            if key not in seen_keys:
                seen_keys.add(key)
                pool.append((entry, pg))

    # Filter out source artist
    pool = [(e, g) for e, g in pool if e['artist'].lower() != artist.lower()]

    # Score each candidate
    scored = []
    for entry, pool_genre in pool:
        score = _score_candidate(entry['artist'], entry['name'], pool_genre, source_profile)
        scored.append((score, entry, pool_genre))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Tighter pool (top 8) → less variance, more on-vibe results.
    # Small jitter (±3) still provides freshness across calls.
    top_pool = scored[:8]
    jittered = [(s + random.uniform(-3, 3), e, g) for s, e, g in top_pool]
    jittered.sort(key=lambda x: x[0], reverse=True)

    # Artist diversity: no artist appears more than once in the final 5.
    # Iterate through the scored list in order; skip duplicate artists.
    result = []
    seen_artists: set = set()
    for _, entry, _pool_genre in jittered:
        ak = entry['artist'].lower()
        if ak not in seen_artists:
            seen_artists.add(ak)
            result.append(dict(entry))
        if len(result) == 5:
            break

    # Safety fallback: if dedup left fewer than 5, pad from remaining scored
    if len(result) < 5:
        for _, entry, _pool_genre in scored:
            if dict(entry) not in result:
                result.append(dict(entry))
            if len(result) == 5:
                break

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Public API (unchanged signatures)
# ──────────────────────────────────────────────────────────────────────────────

def get_similar_songs(artist: str, song: str, mood: str) -> List[Dict]:
    """
    Return 5 recommended songs similar in vibe to the source.
    Unchanged signature — drop-in replacement.
    """
    try:
        genre = _detect_genre(artist, song, mood)
        source_profile = _build_song_profile(artist, song, mood, genre)
        logger.info(
            f"[REC] profile for '{artist} - {song}': "
            f"genre={source_profile['genre']} mood={source_profile['mood']} "
            f"style={source_profile.get('style','?')} "
            f"vocal={source_profile['vocal']} era={source_profile['era']}"
        )

        apple_recs = _get_apple_recommendations(artist, song, source_profile)
        if apple_recs and len(apple_recs) >= 3:
            logger.info(f"[REC] Apple Music (scored) for '{artist} - {song}'")
            return apple_recs

        logger.info(f"[REC] Curated (scored) for '{artist} - {song}'")
        return _get_curated_recommendations(artist, song, mood, source_profile)

    except Exception as e:
        logger.error(f"[REC] Error: {e}")
        genre = _detect_genre_fast(artist)
        source_profile = _build_song_profile(artist, song, mood, genre)
        return _get_curated_recommendations(artist, song, mood, source_profile)


def format_recommendations(recommendations: List[Dict], based_on: str = None) -> str:
    """Format recommendation list — output format unchanged."""
    if not recommendations:
        return "😕 Sorry, I couldn't find recommendations right now. Try another song!"

    header = "🎵 Songs You Might Love\n"
    if based_on:
        header = f"🎵 If you like \"{based_on}\", try these:\n"
    header += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    APPLE_REASON = 'Trending on Apple Music Top 100'
    all_apple = all(s.get('reason') == APPLE_REASON for s in recommendations)

    lines = []
    for i, song in enumerate(recommendations, 1):
        emoji = ['🔥', '✨', '💫', '🎶', '⭐'][i - 1] if i <= 5 else '🎵'
        line = f"{emoji} {song['artist']} — {song['name']}"
        reason = song.get('reason', '')
        if reason and reason != APPLE_REASON:
            line += f"\n   ↳ {reason}"
        elif song.get('match'):
            line += f" ({song['match']}% match)"
        lines.append(line)

    body = '\n\n'.join(lines)
    source_note = "\n🍎 Source: Apple Music Top 100" if all_apple else ""
    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━{source_note}\n"
        "🎤 /lyrics to see any song's lyrics\n"
        "📊 /analyze for deeper insights"
    )

    return header + body + footer
