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
    """Build a lightweight metadata profile dict for a song."""
    ap = _get_artist_profile(artist)
    mood = _infer_mood_from_title(song, genre, handler_mood)
    tempo = _infer_tempo(mood, genre)
    return {
        'genre': genre,
        'mood': mood,
        'vocal': ap.get('vocal', 'male'),
        'tempo': tempo,
        'era': ap.get('era', 'modern'),
    }


def _mood_compat(m1: str, m2: str) -> float:
    """Return compatibility score 0-100 between two moods (symmetric)."""
    return float(_MOOD_COMPAT.get((m1, m2)) or _MOOD_COMPAT.get((m2, m1)) or 20)


def _score_candidate(candidate_artist: str, candidate_name: str,
                     candidate_genre: str, source: Dict) -> float:
    """
    Score a candidate against source profile (0-100, weighted).

    Weights:
      40% mood similarity
      25% genre similarity
      15% vocal similarity
      10% tempo similarity
      10% era similarity
    """
    cp = _get_artist_profile(candidate_artist)
    c_mood = _infer_mood_from_title(candidate_name, candidate_genre, '')
    c_tempo = _infer_tempo(c_mood, candidate_genre)

    mood_score = _mood_compat(c_mood, source['mood'])
    genre_score = 100.0 if candidate_genre == source['genre'] else 20.0
    vocal_score = 100.0 if cp.get('vocal') == source['vocal'] else 40.0
    tempo_score = 100.0 if c_tempo == source['tempo'] else 50.0
    era_score = 100.0 if cp.get('era') == source['era'] else 30.0

    return (
        0.40 * mood_score +
        0.25 * genre_score +
        0.15 * vocal_score +
        0.10 * tempo_score +
        0.10 * era_score
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

    # Check quality: are the top-5 results actually similar in vibe?
    top5_scores = [s for s, _, _ in scored[:5]]
    avg_quality = sum(top5_scores) / len(top5_scores) if top5_scores else 0
    logger.info(f"[REC] Apple top-5 avg score: {avg_quality:.1f} "
                f"(threshold={_APPLE_MIN_QUALITY}) for '{artist} - {song}'")

    if avg_quality < _APPLE_MIN_QUALITY:
        # Curated pool will give better genre/vibe matches — use that instead
        logger.info(f"[REC] Apple quality too low ({avg_quality:.1f}), falling back to curated")
        return None

    # Good quality: take top 10, add jitter, sample 5 for variety
    top_pool = scored[:10]
    jittered = [(s + random.uniform(-4, 4), c, g) for s, c, g in top_pool]
    jittered.sort(key=lambda x: x[0], reverse=True)
    selected = jittered[:5]

    result = []
    for score, c, c_genre in selected:
        rec = dict(c)
        rec['reason'] = _generate_reason(
            c['artist'], c['name'], c_genre, source_profile, c.get('reason', '')
        )
        result.append(rec)

    return result


def _get_curated_recommendations(artist: str, song: str,
                                  mood: str, source_profile: Dict) -> List[Dict]:
    """Score + rank curated genre pool by vibe similarity."""
    genre = source_profile['genre']
    logger.info(f"Curated recs: genre='{genre}' mood='{source_profile['mood']}' "
                f"for '{artist} - {song}'")

    # Build pool: primary genre + related genres
    pool: List[tuple] = []  # (candidate_dict, pool_genre)

    primary = GENRE_RECOMMENDATIONS.get(genre, GENRE_RECOMMENDATIONS['pop'])
    for entry in primary:
        pool.append((entry, genre))

    if len(pool) < 8:
        for rg in MOOD_GENRE_WEIGHTS.get(mood, ['pop']):
            if rg != genre:
                for entry in GENRE_RECOMMENDATIONS.get(rg, []):
                    pool.append((entry, rg))

    # Filter out source artist
    pool = [(e, g) for e, g in pool if e['artist'].lower() != artist.lower()]

    # Score
    scored = []
    for entry, pool_genre in pool:
        score = _score_candidate(entry['artist'], entry['name'], pool_genre, source_profile)
        score += random.uniform(-5, 5)
        scored.append((score, entry, pool_genre))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top 12 and sample 5
    top_pool = scored[:12]
    selected = random.sample(top_pool, min(5, len(top_pool)))

    result = []
    for score, entry, pool_genre in selected:
        rec = dict(entry)
        # Curated entries already have good reasons — keep them
        result.append(rec)

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
            f"vocal={source_profile['vocal']} tempo={source_profile['tempo']} "
            f"era={source_profile['era']}"
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
