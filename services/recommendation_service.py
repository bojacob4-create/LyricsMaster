import os
import re
import logging
import random
import requests
import time
from functools import lru_cache
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
    'jhay cortez': 'latin', 'sech': 'latin', 'anuel aa': 'latin', 'tainy': 'latin',
    'mora': 'latin', 'boza': 'latin', 'quevedo': 'latin', 'maluma': 'latin',
    'nicky jam': 'latin', 'wisin': 'latin', 'yandel': 'latin', 'don omar': 'latin',
    'arcangel': 'latin', 'farruko': 'latin', 'lunay': 'latin', 'darell': 'latin',
    'el alfa': 'latin', 'natanael cano': 'latin', 'junior h': 'latin',
    'becky g': 'latin', 'natti natasha': 'latin', 'sebastian yatra': 'latin',
    'camilo': 'latin', 'dei v': 'latin', 'plan b': 'latin',
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
    # Electronic / dance
    'avicii': 'electronic',          'calvin harris': 'electronic',
    'kygo': 'electronic',            'zedd': 'electronic',
    'marshmello': 'electronic',      'the chainsmokers': 'electronic',
    'martin garrix': 'electronic',   'david guetta': 'electronic',
    'disclosure': 'electronic',      'daft punk': 'electronic',
    'fred again..': 'electronic',    'fred again': 'electronic',
    'skrillex': 'electronic',        'tiesto': 'electronic',
    'tiësto': 'electronic',          'swedish house mafia': 'electronic',
    'deadmau5': 'electronic',        'clean bandit': 'electronic',
    'duke dumont': 'electronic',     'dj snake': 'electronic',
    'diplo': 'electronic',           'flume': 'electronic',
    'odesza': 'electronic',          'bicep': 'electronic',
    'four tet': 'electronic',        'fisher': 'electronic',
    'dom dolla': 'electronic',       'chris lake': 'electronic',
    'caribou': 'electronic',         'tycho': 'electronic',
    # Indie / art-pop / bedroom pop
    'joji': 'indie',                 'omar apollo': 'indie',
    'rex orange county': 'indie',    'still woozy': 'indie',
    'clairo': 'indie',               'surfaces': 'indie',
    'boy pablo': 'indie',            'conan gray': 'indie',
    'phoebe bridgers': 'indie',      'mitski': 'indie',
    'japanese breakfast': 'indie',   'fka twigs': 'indie',
    'bon iver': 'indie',             'james blake': 'indie',
    'sufjan stevens': 'indie',       'beach house': 'indie',
    'the japanese house': 'indie',   'cigarettes after sex': 'indie',
    'snail mail': 'indie',           'men i trust': 'indie',
    'lorde': 'indie',                'aurora': 'indie',
    'birdy': 'indie',                'sigrid': 'indie',
    'halsey': 'indie',               'florence + the machine': 'indie',
    # Downtempo / Trip-hop
    'massive attack': 'electronic',  'portishead': 'electronic',
    'bonobo': 'electronic',          'bjork': 'electronic',
    'tricky': 'electronic',          'thievery corporation': 'electronic',
    'moby': 'electronic',            'jon hopkins': 'electronic',
    # Ambient / Atmospheric electronic
    'brian eno': 'electronic',       'max richter': 'classic',
    'nils frahm': 'classic',         'olafur arnalds': 'classic',
    'tycho': 'electronic',           'hammock': 'electronic',
    # IDM / Experimental electronic
    'aphex twin': 'electronic',      'boards of canada': 'electronic',
    'burial': 'electronic',          'arca': 'electronic',
    # Drum & Bass / UK Garage
    'pendulum': 'electronic',        'chase & status': 'electronic',
    'goldie': 'electronic',          'craig david': 'electronic',
    # Trance
    'armin van buuren': 'electronic','paul van dyk': 'electronic',
    'above & beyond': 'electronic',
    # Neo-soul
    "d'angelo": 'rnb',              'erykah badu': 'rnb',
    'anderson .paak': 'rnb',         'lauryn hill': 'rnb',
    'maxwell': 'rnb',                'india arie': 'rnb',
    'jill scott': 'rnb',             'hiatus kaiyote': 'rnb',
    'gary clark jr.': 'rnb',
    # Post-rock / Art-rock
    'explosions in the sky': 'rock', 'sigur ros': 'rock',
    'sigur rós': 'rock',             'godspeed you! black emperor': 'rock',
    'mogwai': 'rock',                'the national': 'rock',
    'arcade fire': 'rock',           'nick cave': 'rock',
    'st. vincent': 'rock',           'pj harvey': 'rock',
    # Shoegaze
    'my bloody valentine': 'indie',  'slowdive': 'indie',
    'ride': 'indie',                 'cocteau twins': 'indie',
    'nothing': 'indie',              'shoegaze': 'indie',
    # Singer-songwriter / Indie folk
    'noah kahan': 'indie',           'nick drake': 'indie',
    'iron & wine': 'indie',          'damien rice': 'indie',
    'gregory alan isakov': 'indie',  'father john misty': 'indie',
    'simon & garfunkel': 'indie',    'sufjan stevens': 'indie',
    # Cinematic / Orchestral
    'hans zimmer': 'classic',        'ennio morricone': 'classic',
    'ludovico einaudi': 'classic',   'yann tiersen': 'classic',
    'john williams': 'classic',
    # Hip-hop / Trap (chart-active artists commonly mis-defaulting to pop)
    'lil uzi vert': 'hiphop',        'lil baby': 'hiphop',
    'youngboy never broke again': 'hiphop', 'pooh shiesty': 'hiphop',
    'dababy': 'hiphop',              'don toliver': 'hiphop',
    'gunna': 'hiphop',               'lil durk': 'hiphop',
    'polo g': 'hiphop',              'roddy ricch': 'hiphop',
    'a boogie wit da hoodie': 'hiphop', 'a$ap rocky': 'hiphop',
    'a$ap ferg': 'hiphop',           'chief keef': 'hiphop',
    'juice wrld': 'hiphop',          'xxxtentacion': 'hiphop',
    'nba youngboy': 'hiphop',        'jack harlow': 'hiphop',
    'yeat': 'hiphop',                'central cee': 'hiphop',
    'fivio foreign': 'hiphop',       'asap rocky': 'hiphop',
    'quavo': 'hiphop',               'takeoff': 'hiphop',
    'offset': 'hiphop',              'migos': 'hiphop',
    '42 dugg': 'hiphop',             'moneybagg yo': 'hiphop',
    'mozzy': 'hiphop',
    'blxst': 'rnb',                  'mariah the scientist': 'rnb',
    'kehlani': 'rnb',                'giveon': 'rnb',
    'bryson tiller': 'rnb',          'dvsn': 'rnb',
    # Country (chart-active, commonly in Apple Top 100)
    'morgan wallen': 'country',      'luke combs': 'country',
    'ella langley': 'country',       'whiskey myers': 'country',
    'zach bryan': 'country',         'hardy': 'country',
    'tyler hubbard': 'country',      'brett young': 'country',
    'thomas rhett': 'country',       'blake shelton': 'country',
    'dierks bentley': 'country',     'eric church': 'country',
    'chris stapleton': 'country',    'kacey musgraves': 'country',
    'lainey wilson': 'country',      'cody johnson': 'country',
    # Rock / Alt-rock (chart-active, commonly mis-defaulting to pop)
    'dominic fike': 'rock',          'the strokes': 'rock',
    'wallows': 'rock',               'cage the elephant': 'rock',
    'the 1975': 'rock',              'interpol': 'rock',
    'vampire weekend': 'rock',       'beach boys': 'classic',
    'the smiths': 'rock',            'the cure': 'rock',
    'mgmt': 'rock',                  'alt-j': 'rock',
    'glass animals': 'rock',         'the lumineers': 'rock',
    'of monsters and men': 'rock',   'big thief': 'indie',
    'alex g': 'indie',
}

# iTunes genre → internal genre
_ITUNES_GENRE_MAP = {
    'hip-hop/rap': 'hiphop', 'hip hop/rap': 'hiphop', 'hip-hop': 'hiphop',
    'r&b/soul': 'rnb', 'r&b': 'rnb', 'soul': 'rnb',
    'pop': 'pop',
    'electronic': 'electronic', 'dance': 'electronic', 'techno': 'electronic',
    'house': 'electronic', 'trance': 'electronic', 'edm': 'electronic',
    'rock': 'rock', 'alternative': 'rock',
    'indie': 'indie', 'indie pop': 'indie', 'art pop': 'indie',
    'latin': 'latin', 'reggaeton': 'latin', 'latin urban': 'latin',
    'country': 'country', 'jazz': 'classic', 'classical': 'classic',
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
        # Neo-soul representatives
        {"artist": "D'Angelo", 'name': 'Untitled (How Does It Feel)', 'reason': 'Neo-soul masterpiece'},
        {'artist': 'Erykah Badu', 'name': 'On & On', 'reason': 'Neo-soul founding voice'},
        {'artist': 'Anderson .Paak', 'name': 'Come Down', 'reason': 'Neo-soul funk energy'},
        {'artist': 'Lauryn Hill', 'name': 'Ex-Factor', 'reason': 'Neo-soul emotional rawness'},
        {'artist': 'Maxwell', 'name': "Ascension (Don't Ever Wonder)", 'reason': 'Silky neo-soul romance'},
        {'artist': 'Hiatus Kaiyote', 'name': 'Nakamarra', 'reason': 'Neo-soul polyrhythmic wonder'},
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
        # Post-rock / art-rock representatives
        {'artist': 'Explosions in the Sky', 'name': 'The Birth and Death of the Day', 'reason': 'Cinematic post-rock sweep'},
        {'artist': 'Sigur Rós', 'name': 'Svefn-g-englar', 'reason': 'Post-rock ethereal grandeur'},
        {'artist': 'The National', 'name': 'About Today', 'reason': 'Art-rock emotional restraint'},
        {'artist': 'Arcade Fire', 'name': 'Wake Up', 'reason': 'Anthemic art-rock sweep'},
        {'artist': 'St. Vincent', 'name': 'New York', 'reason': 'Art-rock sophistication'},
        {'artist': 'Nick Cave', 'name': 'Into My Arms', 'reason': 'Dark post-punk piano ballad'},
    ],
    'latin': [
        # ── Reggaeton / urbano core ───────────────────────────────────────────
        {'artist': 'Bad Bunny', 'name': 'Titi Me Pregunto', 'reason': 'Dembow reggaeton energy'},
        {'artist': 'Bad Bunny', 'name': 'Monaco', 'reason': 'Latin trap minimalism'},
        {'artist': 'Bad Bunny', 'name': 'Un Verano Sin Ti', 'reason': 'Chill Latin summer feel'},
        {'artist': 'Karol G', 'name': 'BICHOTA', 'reason': 'Reggaeton confidence anthem'},
        {'artist': 'Karol G', 'name': 'Provenza', 'reason': 'Latin urban club energy'},
        {'artist': 'Rauw Alejandro', 'name': 'Todo de Ti', 'reason': 'Modern Latin pop-reggaeton'},
        {'artist': 'Rauw Alejandro', 'name': 'Lokera', 'reason': 'Uptempo reggaeton flow'},
        {'artist': 'Feid', 'name': 'Chorrito Pa Las Animas', 'reason': 'Chill urbano groove'},
        {'artist': 'Feid', 'name': 'Normal', 'reason': 'Latin R&B-urbano fusion'},
        {'artist': 'Myke Towers', 'name': 'La Inocente', 'reason': 'Smooth reggaeton flow'},
        {'artist': 'Myke Towers', 'name': 'Almas Gemelas', 'reason': 'Latin trap romance'},
        {'artist': 'Jhay Cortez', 'name': 'Dakiti', 'reason': 'Atmospheric Latin trap'},
        {'artist': 'Jhay Cortez', 'name': 'No Me Conoce', 'reason': 'Slow-burn Latin urban'},
        {'artist': 'Ozuna', 'name': 'Taki Taki', 'reason': 'Global reggaeton anthem'},
        {'artist': 'J Balvin', 'name': 'Con Altura', 'reason': 'Classic reggaeton crossover'},
        {'artist': 'J Balvin', 'name': 'Mi Gente', 'reason': 'Latin club floor-filler'},
        {'artist': 'Daddy Yankee', 'name': 'Gasolina', 'reason': 'Foundational reggaeton energy'},
        {'artist': 'Daddy Yankee', 'name': 'Dura', 'reason': 'High-tempo reggaeton anthem'},
        {'artist': 'Sech', 'name': 'Otro Trago', 'reason': 'Tropical reggaeton groove'},
        {'artist': 'Anuel AA', 'name': 'China', 'reason': 'Hard Latin trap/reggaeton'},
        {'artist': 'Tainy', 'name': 'Lo Siento BB://', 'reason': 'Experimental Latin urban'},
        {'artist': 'Mora', 'name': 'Colombia', 'reason': 'Melodic Latin urban'},
        {'artist': 'Quevedo', 'name': 'Columbia', 'reason': 'Spanish-urban crossover'},
        {'artist': 'Boza', 'name': 'Hecha Pa Mi', 'reason': 'Smooth urbano Caribbean feel'},
        {'artist': 'Maluma', 'name': 'Hawái', 'reason': 'Chill Latin pop-reggaeton'},
        # ── Latin pop / crossover ─────────────────────────────────────────────
        {'artist': 'Rosalía', 'name': 'DESPECHA', 'reason': 'Spanish flamenco-urban fusion'},
        {'artist': 'Shakira', 'name': 'Bzrp Music Sessions #53', 'reason': 'Global Latin pop moment'},
        {'artist': 'Karol G', 'name': 'Mañana Será Bonito', 'reason': 'Latin pop anthem 2023'},
        {'artist': 'Anitta', 'name': 'Funk Rave', 'reason': 'Brazilian funk-urban crossover'},
        {'artist': 'Becky G', 'name': 'Mamiii', 'reason': 'Empowerment Latin pop'},
        # ── Regional Mexican / corridos ───────────────────────────────────────
        {'artist': 'Peso Pluma', 'name': 'Ella Baila Sola', 'reason': 'Corridos tumbados breakout'},
        {'artist': 'Peso Pluma', 'name': 'BZRP Music Sessions #55', 'reason': 'Corridos crossover moment'},
        {'artist': 'Natanael Cano', 'name': 'Amor Tumbado', 'reason': 'Trap-corridos fusion'},
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
        # Cinematic / neoclassical / orchestral representatives
        {'artist': 'Hans Zimmer', 'name': 'Time', 'reason': 'Cinematic orchestral masterpiece'},
        {'artist': 'Ludovico Einaudi', 'name': 'Experience', 'reason': 'Neoclassical piano meditation'},
        {'artist': 'Max Richter', 'name': 'On the Nature of Daylight', 'reason': 'Contemporary classical beauty'},
        {'artist': 'Nils Frahm', 'name': 'Says', 'reason': 'Minimalist piano electronic blend'},
        {'artist': 'Ólafur Arnalds', 'name': 'Near Light', 'reason': 'Ambient neoclassical warmth'},
        {'artist': 'Yann Tiersen', 'name': 'La Valse d\'Amélie', 'reason': 'Cinematic French piano poetry'},
    ],
    'electronic': [
        {'artist': 'Avicii', 'name': 'Wake Me Up', 'reason': 'Festival EDM with folk-pop crossover'},
        {'artist': 'Calvin Harris', 'name': 'Feel So Close', 'reason': 'Dance-electronic euphoria'},
        {'artist': 'Kygo', 'name': 'Firestone', 'reason': 'Chilled tropical EDM'},
        {'artist': 'Zedd', 'name': 'The Middle', 'reason': 'Pop-EDM crossover energy'},
        {'artist': 'Daft Punk', 'name': 'Get Lucky', 'reason': 'Funk-electronic classic'},
        {'artist': 'Disclosure', 'name': 'Latch', 'reason': 'UK garage meets dance pop'},
        {'artist': 'The Chainsmokers', 'name': 'Something Just Like This', 'reason': 'Electronic-pop ballad'},
        {'artist': 'Martin Garrix', 'name': 'Animals', 'reason': 'Big room EDM power'},
        {'artist': 'David Guetta', 'name': 'Titanium', 'reason': 'Anthemic electronic production'},
        {'artist': 'Swedish House Mafia', 'name': "Don't You Worry Child", 'reason': 'Melodic progressive house'},
        {'artist': 'Clean Bandit', 'name': 'Rather Be', 'reason': 'Classical-electronic crossover'},
        {'artist': 'Duke Dumont', 'name': 'Ocean Drive', 'reason': 'Deep house summer anthem'},
        {'artist': 'Marshmello', 'name': 'Alone', 'reason': 'Future bass emotional drive'},
        {'artist': 'Fred again..', 'name': 'Bleed', 'reason': 'UK dance-electronic intimacy'},
        {'artist': 'ODESZA', 'name': 'A Moment Apart', 'reason': 'Indie-electronic cinematic sweep'},
        {'artist': 'Flume', 'name': 'Never Be Like You', 'reason': 'Electronic R&B crossover'},
        {'artist': 'Deadmau5', 'name': 'Strobe', 'reason': 'Progressive house masterpiece'},
        {'artist': 'Tiësto', 'name': 'The Business', 'reason': 'Dance floor EDM 2020'},
        # Downtempo / trip-hop representatives (low-energy cinematic end of electronic)
        {'artist': 'Massive Attack', 'name': 'Teardrop', 'reason': 'Trip-hop atmospheric depth'},
        {'artist': 'Portishead', 'name': 'Glory Box', 'reason': 'Dark atmospheric trip-hop tension'},
        {'artist': 'Bonobo', 'name': 'Kiara', 'reason': 'Lush cinematic downtempo groove'},
        {'artist': 'Burial', 'name': 'Archangel', 'reason': 'UK garage electronic soul'},
        {'artist': 'Jon Hopkins', 'name': 'Emerald Rush', 'reason': 'Melodic electronic introspection'},
        {'artist': 'Moby', 'name': 'Porcelain', 'reason': 'Ambient electronic atmosphere'},
        # Drum & bass / IDM
        {'artist': 'Pendulum', 'name': 'Watercolour', 'reason': 'Drum & bass with rock crossover'},
        # Synthwave / retro-electronic
        {'artist': 'Kavinsky', 'name': 'Nightcall', 'reason': 'Dark synthwave cinematic drive'},
        {'artist': 'The Midnight', 'name': 'Los Angeles', 'reason': 'Nostalgic 80s synthwave storytelling'},
        {'artist': 'Com Truise', 'name': 'Flightwave', 'reason': 'Slowed-down synthwave haze'},
        {'artist': 'Gunship', 'name': 'Tech Noir', 'reason': 'Cinematic dark synthwave atmosphere'},
        # Indie-electronic / chillwave
        {'artist': 'M83', 'name': 'Midnight City', 'reason': 'Anthemic indie-electronic dream-pop'},
        {'artist': 'Washed Out', 'name': 'Feel It All Around', 'reason': 'Chillwave hazy indie-electronic'},
        {'artist': 'Toro y Moi', 'name': 'Still Sound', 'reason': 'Chillwave indie-electronic groove'},
        {'artist': 'Chvrches', 'name': 'The Mother We Share', 'reason': 'Synth-pop indie-electronic anthems'},
        {'artist': 'Tycho', 'name': 'Awake', 'reason': 'Chillwave instrumental warmth'},
        # Nu-disco / disco-electronic
        {'artist': 'Chromeo', 'name': "Jealous (I Ain't With It)", 'reason': 'Nu-disco electro-funk groove'},
        {'artist': 'LCD Soundsystem', 'name': 'All My Friends', 'reason': 'Danceable post-punk electronic'},
        {'artist': 'Hot Chip', 'name': 'Ready for the Floor', 'reason': 'Nu-disco electro-funk anthems'},
        {'artist': 'Breakbot', 'name': "Baby I'm Yours", 'reason': 'French nu-disco swing'},
    ],
    'indie': [
        {'artist': 'Joji', 'name': 'Glimpse of Us', 'reason': 'Emotional lo-fi indie pop'},
        {'artist': 'Rex Orange County', 'name': 'Loving Is Easy', 'reason': 'Sunny indie pop warmth'},
        {'artist': 'Clairo', 'name': 'Sofia', 'reason': 'Soft bedroom pop intimacy'},
        {'artist': 'Surfaces', 'name': 'Sunday Best', 'reason': 'Feel-good indie pop'},
        {'artist': 'Conan Gray', 'name': 'Heather', 'reason': 'Indie pop storytelling'},
        {'artist': 'Omar Apollo', 'name': 'Evergreen', 'reason': 'Indie R&B with lush production'},
        {'artist': 'Still Woozy', 'name': 'Goodie Bag', 'reason': 'Indie bedroom pop energy'},
        {'artist': 'Phoebe Bridgers', 'name': 'Savior Complex', 'reason': 'Alt-folk emotional depth'},
        {'artist': 'Bon Iver', 'name': 'Skinny Love', 'reason': 'Indie folk minimalism'},
        {'artist': 'James Blake', 'name': 'Retrograde', 'reason': 'Electronic indie soul'},
        {'artist': 'FKA twigs', 'name': 'cellophane', 'reason': 'Avant-garde art pop'},
        {'artist': 'Mitski', 'name': 'Nobody', 'reason': 'Indie rock with art-pop drama'},
        {'artist': 'Beach House', 'name': 'Space Song', 'reason': 'Dream pop haze'},
        {'artist': 'Japanese Breakfast', 'name': 'Paprika', 'reason': 'Indie pop with orchestral lift'},
        {'artist': 'Lorde', 'name': 'Royals', 'reason': 'Minimalist indie pop anthem'},
        {'artist': 'Men I Trust', 'name': 'Show Me How', 'reason': 'Dream pop synth softness'},
        {'artist': 'Cigarettes After Sex', 'name': 'Apocalypse', 'reason': 'Slowcore dream pop atmosphere'},
        {'artist': 'The Japanese House', 'name': 'Saw It Coming', 'reason': 'Electronic indie pop'},
        # Shoegaze / dream-pop texture
        {'artist': 'Slowdive', 'name': 'When the Sun Hits', 'reason': 'Shoegaze luminous wash'},
        {'artist': 'Cocteau Twins', 'name': 'Heaven or Las Vegas', 'reason': 'Dream pop ethereal shimmer'},
        # Singer-songwriter / indie folk
        {'artist': 'Noah Kahan', 'name': 'Stick Season', 'reason': 'Singer-songwriter grounded emotion'},
        {'artist': 'Iron & Wine', 'name': 'Naked As We Came', 'reason': 'Indie folk whisper-quiet intimacy'},
        {'artist': 'Damien Rice', 'name': 'The Blower\'s Daughter', 'reason': 'Raw singer-songwriter ache'},
        {'artist': 'Nick Drake', 'name': 'Pink Moon', 'reason': 'Intimate indie folk classic'},
        # Art-rock adjacent
        {'artist': 'Sigur Rós', 'name': 'Hoppípolla', 'reason': 'Post-rock emotional sweep'},
    ],
}

MOOD_GENRE_WEIGHTS = {
    'energetic': ['afrobeats', 'pop', 'hiphop', 'rock', 'electronic'],
    'romantic':  ['rnb', 'pop', 'latin', 'indie'],
    'happy':     ['pop', 'afrobeats', 'latin', 'electronic'],
    'sad':       ['rnb', 'pop', 'rock', 'indie'],
    'relaxed':   ['rnb', 'pop', 'classic', 'indie'],
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
    # New style families
    'downtempo': 'cinematic',    'ambient': 'cinematic',
    'idm': 'electronic',         'techno': 'electronic',
    'trance': 'electronic',      'drum_bass': 'electronic',
    'uk_garage': 'electronic',
    'post_rock': 'band',         'art_rock': 'band',
    'shoegaze': 'band',          'neo_soul': 'minimal',
    'singer_songwriter': 'acoustic',
    'cinematic_score': 'cinematic',
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
    'jhay cortez': 'reggaeton',
    'sech': 'reggaeton',
    'anuel aa': 'reggaeton',
    'arcangel': 'reggaeton',
    'mora': 'reggaeton',
    'boza': 'reggaeton',
    'dei v': 'reggaeton',
    'quevedo': 'reggaeton',
    'maluma': 'reggaeton',
    'nicky jam': 'reggaeton',
    'wisin': 'reggaeton',
    'wisin & yandel': 'reggaeton',
    'yandel': 'reggaeton',
    'plan b': 'reggaeton',
    'don omar': 'reggaeton',
    'tainy': 'reggaeton',
    'el alfa': 'reggaeton',
    'lunay': 'reggaeton',
    'darell': 'reggaeton',
    'farruko': 'reggaeton',
    'zion & lennox': 'reggaeton',
    'peso pluma': 'regional_mexican',
    'natanael cano': 'regional_mexican',
    'junior h': 'regional_mexican',
    'shakira': 'latin_pop',
    'anitta': 'latin_pop',
    'rosalia': 'latin_pop',
    'becky g': 'latin_pop',
    'natti natasha': 'latin_pop',
    'sebastian yatra': 'latin_pop',
    'camilo': 'latin_pop',
    'sofia carson': 'latin_pop',
    # ── Dream pop / Cinematic pop ─────────────────────────────────────────────
    'lana del rey': 'dream_pop',
    'cigarettes after sex': 'dream_pop',
    'beach house': 'dream_pop',
    'the xx': 'dream_pop',
    'mazzy star': 'dream_pop',
    'aurora': 'cinematic_pop',
    'birdy': 'cinematic_pop',
    'lorde': 'cinematic_pop',
    'halsey': 'synth_pop',
    'sigrid': 'cinematic_pop',
    'florence + the machine': 'cinematic_pop',
    'mitski': 'cinematic_pop',
    'phoebe bridgers': 'dream_pop',
    'boygenius': 'dream_pop',
    # ── Synthwave ─────────────────────────────────────────────────────────────
    'kavinsky': 'synthwave',
    'the midnight': 'synthwave',
    'gunship': 'synthwave',
    'perturbator': 'synthwave',
    'com truise': 'synthwave',
    'neon indian': 'synthwave',
    # ── Indie Electronic / Chillwave ──────────────────────────────────────────
    'm83': 'indie_electronic',
    'washed out': 'indie_electronic',
    'toro y moi': 'indie_electronic',
    'odesza': 'indie_electronic',
    'chvrches': 'synth_pop',
    'alt-j': 'indie_electronic',
    'chromatics': 'dream_pop',
    # ── Nu-Disco / Disco-Electronic ───────────────────────────────────────────
    'chromeo': 'nu_disco',
    'lcd soundsystem': 'nu_disco',
    'hot chip': 'nu_disco',
    'breakbot': 'nu_disco',
    'nile rodgers': 'nu_disco',
    # ── Electronic / EDM ─────────────────────────────────────────────────────
    'daft punk': 'nu_disco',
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
    # ── Downtempo / Trip-hop ──────────────────────────────────────────────────
    'massive attack': 'downtempo',
    'portishead': 'downtempo',
    'bonobo': 'downtempo',
    'bjork': 'downtempo',
    'tricky': 'downtempo',
    'thievery corporation': 'downtempo',
    'archive': 'downtempo',
    # ── Ambient / Atmospheric electronic ─────────────────────────────────────
    'moby': 'ambient',
    'brian eno': 'ambient',
    'jon hopkins': 'ambient',
    'tycho': 'indie_electronic',
    'hammock': 'ambient',
    # ── IDM / Experimental electronic ────────────────────────────────────────
    'aphex twin': 'idm',
    'boards of canada': 'idm',
    'burial': 'idm',
    'arca': 'idm',
    # ── Techno / Minimal techno ───────────────────────────────────────────────
    'nina kraviz': 'techno',
    'charlotte de witte': 'techno',
    'objekt': 'techno',
    # ── Trance / Progressive trance ───────────────────────────────────────────
    'armin van buuren': 'trance',
    'paul van dyk': 'trance',
    'ferry corsten': 'trance',
    # ── Drum & Bass ───────────────────────────────────────────────────────────
    'pendulum': 'drum_bass',
    'chase & status': 'drum_bass',
    'goldie': 'drum_bass',
    # ── UK Garage ─────────────────────────────────────────────────────────────
    'craig david': 'uk_garage',
    # ── Post-rock ─────────────────────────────────────────────────────────────
    'explosions in the sky': 'post_rock',
    'godspeed you! black emperor': 'post_rock',
    'mogwai': 'post_rock',
    'sigur ros': 'post_rock',
    'sigur rós': 'post_rock',
    'russian circles': 'post_rock',
    # ── Art-rock / Experimental rock ─────────────────────────────────────────
    'the national': 'art_rock',
    'arcade fire': 'art_rock',
    'nick cave': 'art_rock',
    'st. vincent': 'art_rock',
    'pj harvey': 'art_rock',
    'talking heads': 'art_rock',
    # ── Shoegaze ──────────────────────────────────────────────────────────────
    'my bloody valentine': 'shoegaze',
    'slowdive': 'shoegaze',
    'ride': 'shoegaze',
    'cocteau twins': 'shoegaze',
    # ── Neo-soul ──────────────────────────────────────────────────────────────
    "d'angelo": 'neo_soul',
    'erykah badu': 'neo_soul',
    'anderson .paak': 'neo_soul',
    'lauryn hill': 'neo_soul',
    'maxwell': 'neo_soul',
    'india arie': 'neo_soul',
    'jill scott': 'neo_soul',
    'hiatus kaiyote': 'neo_soul',
    # ── Singer-songwriter / Folk ──────────────────────────────────────────────
    'noah kahan': 'singer_songwriter',
    'nick drake': 'singer_songwriter',
    'iron & wine': 'singer_songwriter',
    'damien rice': 'singer_songwriter',
    'gregory alan isakov': 'singer_songwriter',
    'father john misty': 'singer_songwriter',
    'simon & garfunkel': 'singer_songwriter',
    # ── Cinematic score / Orchestral ──────────────────────────────────────────
    'hans zimmer': 'cinematic_score',
    'ennio morricone': 'cinematic_score',
    'ludovico einaudi': 'cinematic_score',
    'max richter': 'cinematic_score',
    'nils frahm': 'cinematic_score',
    'olafur arnalds': 'cinematic_score',
    'yann tiersen': 'cinematic_score',
    'john williams': 'cinematic_score',
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
    # ── Synthwave family ──────────────────────────────────────────────────────
    ('synthwave', 'synthwave'): 100,
    ('synthwave', 'nu_disco'): 60,
    ('synthwave', 'indie_electronic'): 52,
    ('synthwave', 'dance_electronic'): 40,
    ('synthwave', 'dream_pop'): 42,
    ('synthwave', 'synth_pop'): 48,
    ('synthwave', 'downtempo'): 48,
    ('synthwave', 'ambient'): 38,
    ('synthwave', 'festival_edm'): 15,
    ('synthwave', 'house'): 20,
    ('synthwave', 'dance_pop'): 20,
    ('synthwave', 'trap'): 5,
    ('synthwave', 'country'): 3,
    # ── Indie electronic / chillwave ──────────────────────────────────────────
    ('indie_electronic', 'indie_electronic'): 100,
    ('indie_electronic', 'synthwave'): 52,
    ('indie_electronic', 'dream_pop'): 62,
    ('indie_electronic', 'ambient'): 58,
    ('indie_electronic', 'downtempo'): 55,
    ('indie_electronic', 'synth_pop'): 45,
    ('indie_electronic', 'nu_disco'): 40,
    ('indie_electronic', 'alt_pop'): 42,
    ('indie_electronic', 'dance_electronic'): 28,
    ('indie_electronic', 'house'): 25,
    ('indie_electronic', 'festival_edm'): 10,
    ('indie_electronic', 'dance_pop'): 18,
    ('indie_electronic', 'trap'): 5,
    ('indie_electronic', 'country'): 3,
    # ── Nu-disco / Disco-electronic ───────────────────────────────────────────
    ('nu_disco', 'nu_disco'): 100,
    ('nu_disco', 'dance_pop'): 68,
    ('nu_disco', 'house'): 72,
    ('nu_disco', 'dance_electronic'): 65,
    ('nu_disco', 'synthwave'): 60,
    ('nu_disco', 'synth_pop'): 50,
    ('nu_disco', 'pop_rnb'): 48,
    ('nu_disco', 'indie_electronic'): 40,
    ('nu_disco', 'indie_rock'): 30,
    ('nu_disco', 'festival_edm'): 25,
    ('nu_disco', 'trap'): 8,
    ('nu_disco', 'country'): 3,
}


# Maps each style to the curated genre pool that contains the best candidates.
# Used to cross-search the right pool even when detected genre differs.
STYLE_GENRE_AFFINITY: Dict[str, str] = {
    # Pop families
    'dance_pop': 'pop',      'synth_pop': 'pop',      'emotional_pop': 'pop',
    'pop_rnb': 'rnb',
    # R&B families
    'alt_rnb': 'rnb',        'smooth_rnb': 'rnb',     'emotional_rnb': 'rnb',
    'sensual_rnb': 'rnb',    'soul': 'rnb',
    # Afrobeats families
    'afrobeats': 'afrobeats', 'afro_fusion': 'afrobeats', 'amapiano': 'afrobeats',
    # Hip-hop families
    'trap': 'hiphop',        'melodic_rap': 'hiphop', 'lyrical_rap': 'hiphop',
    'female_rap': 'hiphop',
    # Latin families
    'reggaeton': 'latin',    'latin_pop': 'latin',    'regional_mexican': 'latin',
    # Rock families
    'indie_rock': 'rock',    'alt_rock': 'rock',      'anthemic_rock': 'rock',
    'folk_rock': 'rock',     'punk_pop': 'rock',      'psychedelic_rock': 'rock',
    'classic_rock': 'classic',
    # Electronic families → dedicated electronic pool
    'dance_electronic': 'electronic',
    'festival_edm': 'electronic',
    'house': 'electronic',
    'downtempo': 'electronic',
    'ambient': 'electronic',
    'idm': 'electronic',
    'techno': 'electronic',
    'trance': 'electronic',
    'drum_bass': 'electronic',
    'uk_garage': 'electronic',
    'synthwave': 'electronic',
    'indie_electronic': 'electronic',
    'nu_disco': 'electronic',
    # Rock sub-families → rock pool
    'post_rock': 'rock',
    'art_rock': 'rock',
    # Indie / art-pop / shoegaze / folk families → indie pool
    'dream_pop': 'indie',    'cinematic_pop': 'indie',
    'alt_pop': 'indie',      'acoustic_pop': 'indie',
    'lo_fi': 'indie',        'art_pop': 'indie',
    'indie_folk': 'indie',   'shoegaze': 'indie',
    'singer_songwriter': 'indie',
    # Neo-soul → rnb pool
    'neo_soul': 'rnb',
    # Cinematic / orchestral → classic pool
    'cinematic_score': 'classic',
}

# ──────────────────────────────────────────────────────────────────────────────
# Sonic Pool Hint  — song-first candidate expansion
# ──────────────────────────────────────────────────────────────────────────────
# Maps (mood, production) → one additional pool to include in candidate search.
# This fires for EVERY query, regardless of detected artist genre.
# It lets the song's own emotional+sonic character reach pools that the
# artist-genre routing would otherwise miss (e.g. a slow electronic track
# finding the downtempo end of the electronic pool, or a melancholic pop song
# finding folk-adjacent indie candidates).
# There are no artist names here — this is purely a song-characteristic signal.
SONIC_POOL_HINT: Dict[tuple, str] = {
    # Cinematic feel: downtempo/ambient end of electronic pool
    ('sad',       'cinematic'):  'electronic',
    ('relaxed',   'cinematic'):  'electronic',
    # Acoustic feel: indie/folk pool
    ('sad',       'acoustic'):   'indie',
    ('relaxed',   'acoustic'):   'indie',
    ('romantic',  'acoustic'):   'indie',
    ('romantic',  'cinematic'):  'indie',
    # Stripped-down emotional: R&B/soul pool
    ('sad',       'minimal'):    'rnb',
    ('relaxed',   'minimal'):    'rnb',
    ('romantic',  'minimal'):    'rnb',
    # High-energy: domain-specific pools
    ('energetic', 'band'):       'rock',
    ('energetic', 'trap'):       'hiphop',
    ('energetic', 'mixed'):      'afrobeats',
    ('happy',     'mixed'):      'afrobeats',
    ('romantic',  'mixed'):      'latin',
    ('happy',     'electronic'): 'electronic',
    ('energetic', 'electronic'): 'electronic',
}

# ──────────────────────────────────────────────────────────────────────────────
# Ecosystem map — structural hierarchy for cross-genre leakage prevention
# ──────────────────────────────────────────────────────────────────────────────
# Every curated pool belongs to one broad musical ecosystem.  All pool
# expansion (sonic hint, mood expansion) and constellation-bonus gating
# check this map to ensure candidates stay within the source song's
# musical family.  Adjacency is symmetric in effect but explicit in direction:
# including ecosystem B in A's adjacent set means an A-source song may cross
# into B's pool; the reverse is also defined where it makes musical sense.

POOL_ECOSYSTEM: Dict[str, str] = {
    'pop':        'pop_synth',
    'electronic': 'electronic_synth',
    'hiphop':     'hiphop_trap',
    'rnb':        'rnb_soul',
    'rock':       'rock_band',
    'indie':      'indie_alt',
    'afrobeats':  'afrobeats_world',
    'latin':      'afrobeats_world',
    'classic':    'classical_cinematic',
    'country':    'country_folk',
}

# Each ecosystem's adjacent set (always includes itself).
# Pools whose ecosystem is NOT in this set are blocked from entering the
# candidate list via hint/expansion, and from receiving the constellation bonus.
ECOSYSTEM_ADJACENT: Dict[str, frozenset] = {
    'pop_synth':          frozenset({'pop_synth', 'electronic_synth',
                                     'indie_alt',  'rnb_soul'}),
    'electronic_synth':   frozenset({'electronic_synth', 'pop_synth',
                                     'indie_alt',  'classical_cinematic'}),
    'hiphop_trap':        frozenset({'hiphop_trap', 'rnb_soul', 'pop_synth'}),
    'rnb_soul':           frozenset({'rnb_soul',    'hiphop_trap', 'pop_synth'}),
    'rock_band':          frozenset({'rock_band',   'indie_alt'}),
    'indie_alt':          frozenset({'indie_alt',   'rock_band',
                                     'pop_synth',   'electronic_synth'}),
    'afrobeats_world':    frozenset({'afrobeats_world', 'rnb_soul', 'pop_synth',
                                     'hiphop_trap'}),
    'classical_cinematic':frozenset({'classical_cinematic', 'indie_alt',
                                     'electronic_synth'}),
    'country_folk':       frozenset({'country_folk', 'indie_alt'}),
}

# ──────────────────────────────────────────────────────────────────────────────
# Production → Ecosystem priority table
# ──────────────────────────────────────────────────────────────────────────────
# Maps (production_signature, style_pool_hint) → ecosystem.
# style_pool_hint = STYLE_GENRE_AFFINITY.get(style, '') — the curated pool that
# the song's style family routes to.  This refines ambiguous production values
# (e.g. 'cinematic' can be orchestral OR electronic downtempo, distinguished by
# whether the style routes to 'classic' or 'electronic').
#
# Design principle: production is the PRIMARY signal for ecosystem identity;
# it overrides the artist's broad genre classification.  A disco/funk track
# classified as 'pop' genre gets electronic_synth ecosystem because its
# production signature IS electronic.  Mood is never consulted here.
_PROD_POOL_ECOSYSTEM: Dict[tuple, str] = {
    # Electronic production — ALWAYS electronic_synth regardless of origin genre.
    # Covers synth-pop, dance-electronic, disco, house, EDM, trance, etc.
    ('electronic', 'electronic'): 'electronic_synth',
    ('electronic', 'pop'):        'electronic_synth',   # synth-pop crossover
    ('electronic', 'indie'):      'electronic_synth',   # electronic indie
    ('electronic', 'rnb'):        'electronic_synth',   # electronic R&B
    ('electronic', 'hiphop'):     'electronic_synth',   # electronic rap
    ('electronic', ''):           'electronic_synth',   # any unrouted style
    # Trap production — always hiphop territory.
    ('trap', 'hiphop'):           'hiphop_trap',
    ('trap', 'rnb'):              'hiphop_trap',         # melodic rap
    ('trap', 'pop'):              'hiphop_trap',         # pop-rap
    ('trap', ''):                 'hiphop_trap',
    # Band/guitar production — rock or indie based on style routing.
    ('band', 'rock'):             'rock_band',
    ('band', 'indie'):            'indie_alt',
    ('band', 'pop'):              'pop_synth',           # pop-rock crossover
    ('band', ''):                 'rock_band',
    # Acoustic production — indie/folk territory; classical for classical styles.
    ('acoustic', 'indie'):        'indie_alt',
    ('acoustic', 'rock'):         'indie_alt',           # acoustic rock = indie-adjacent
    ('acoustic', 'classic'):      'classical_cinematic',
    ('acoustic', 'pop'):          'indie_alt',           # acoustic pop → indie pool
    ('acoustic', ''):             'indie_alt',
    # Cinematic production — electronic downtempo vs classical vs indie-cinematic.
    # Resolved by which pool the style routes to.
    ('cinematic', 'electronic'):  'electronic_synth',    # trip-hop, downtempo, ambient
    ('cinematic', 'classic'):     'classical_cinematic', # orchestral, neoclassical
    ('cinematic', 'indie'):       'indie_alt',           # cinematic indie, dream-pop
    ('cinematic', 'pop'):         'pop_synth',           # cinematic pop
    ('cinematic', ''):            'classical_cinematic', # safety net — rarely fires
    # Minimal production — stripped R&B/soul or melodic hiphop.
    ('minimal', 'rnb'):           'rnb_soul',
    ('minimal', 'hiphop'):        'hiphop_trap',         # melodic/sad rap
    ('minimal', 'pop'):           'rnb_soul',            # minimal pop leans R&B
    ('minimal', 'indie'):         'indie_alt',
    ('minimal', ''):              'rnb_soul',
    # Latin urban production — reggaeton/dembow beat is electronic in construction
    # but belongs to the Latin urban ecosystem, NOT electronic_synth.
    # This entry fires when style_pool='latin' and production='electronic'
    # (which is the path for reggaeton / latin trap / dembow).
    ('electronic', 'latin'):  'afrobeats_world',
    ('mixed',      'latin'):  'afrobeats_world',  # latin_pop, regional_mexican
    ('trap',       'latin'):  'afrobeats_world',  # latin trap
    # Mixed production — no strong production identity; falls through to genre.
    # (no entries intentionally — let style_pool → genre fallback handle it)
}

# ──────────────────────────────────────────────────────────────────────────────
# Production signature classifier — finer-grained taxonomy for ecosystem id
# ──────────────────────────────────────────────────────────────────────────────
# The production-feel taxonomy (electronic/trap/band/…) is coarse-grained and
# ignores genre context.  The production signature taxonomy below is finer,
# using (style, genre) pairs to resolve ambiguous styles such as alt_pop or
# emotional_pop where the genre context changes the correct sonic identity.
# Mood is NEVER used here; this is a structural assignment only.
#
# Signature vocabulary:
#   electronic_synth  — synth/electronic textures (synth-pop, EDM, house, etc.)
#   disco_funk        — disco/funk-influenced electronic (high-BPM dance-pop)
#   band_rock         — live guitar-band production
#   acoustic_minimal  — organic acoustic/singer-songwriter production
#   trap_beats        — trap and hip-hop beat production
#   rnb_soul          — R&B / soul texture production
#   indie_alt         — indie / alternative production
#   cinematic         — orchestral/ambient/cinematic (resolved downstream)

# (style, genre) → production_signature
_PROD_SIGNATURE_MAP: Dict[tuple, str] = {
    # Alt-pop disambiguation: alt_pop maps to 'mixed' feel, but genre context
    # reveals the true sonic territory.
    ('alt_pop', 'pop'):   'electronic_synth',  # modern synth-flavoured alt-pop
    ('alt_pop', 'rnb'):   'rnb_soul',           # R&B-flavoured alt-pop
    ('alt_pop', 'indie'): 'indie_alt',           # indie-flavoured alt-pop
    ('alt_pop', 'rock'):  'band_rock',           # rock-flavoured alt-pop
    # Emotional-pop disambiguation
    ('emotional_pop', 'pop'):   'acoustic_minimal',  # piano/acoustic ballad
    ('emotional_pop', 'rnb'):   'rnb_soul',           # R&B ballad
    ('emotional_pop', 'indie'): 'indie_alt',          # indie ballad
    # Dance-pop: disco/funk texture vs straight electronic
    ('dance_pop', 'pop'):   'disco_funk',        # disco-funk influenced pop
    ('dance_pop', 'rnb'):   'electronic_synth',  # electronic R&B dance
    # Synth-pop: always electronic regardless of the artist's origin genre
    ('synth_pop', 'pop'):   'electronic_synth',
    ('synth_pop', 'rnb'):   'electronic_synth',  # e.g. synth-pop R&B artists
    ('synth_pop', 'indie'): 'electronic_synth',
    # Pop-R&B crossover: electronic in both directions
    ('pop_rnb', 'rnb'):   'electronic_synth',
    ('pop_rnb', 'pop'):   'electronic_synth',
    # Pure electronic styles (confirming by genre)
    ('festival_edm', 'electronic'): 'electronic_synth',
    ('festival_edm', 'pop'):        'disco_funk',
    ('house',        'electronic'): 'electronic_synth',
    ('techno',       'electronic'): 'electronic_synth',
    ('trance',       'electronic'): 'electronic_synth',
    ('idm',          'electronic'): 'electronic_synth',
    ('drum_bass',    'electronic'): 'electronic_synth',
    ('uk_garage',    'electronic'): 'electronic_synth',
    # Downtempo / trip-hop / ambient: cinematic feel, electronic ecosystem
    ('downtempo', 'electronic'): 'cinematic',
    ('ambient',   'electronic'): 'cinematic',
    # Trap / hip-hop beats
    ('trap',         'hiphop'): 'trap_beats',
    ('lyrical_rap',  'hiphop'): 'trap_beats',
    ('melodic_rap',  'hiphop'): 'trap_beats',
    ('female_rap',   'hiphop'): 'trap_beats',
    # R&B / soul families
    ('alt_rnb',      'rnb'): 'rnb_soul',
    ('smooth_rnb',   'rnb'): 'rnb_soul',
    ('emotional_rnb','rnb'): 'rnb_soul',
    ('sensual_rnb',  'rnb'): 'rnb_soul',
    ('soul',         'rnb'): 'rnb_soul',
    ('neo_soul',     'rnb'): 'rnb_soul',
    # Guitar-band production
    ('indie_rock',      'rock'):    'band_rock',
    ('alt_rock',        'rock'):    'band_rock',
    ('anthemic_rock',   'rock'):    'band_rock',
    ('post_rock',       'rock'):    'band_rock',
    ('art_rock',        'rock'):    'band_rock',
    ('psychedelic_rock','rock'):    'band_rock',
    ('classic_rock',    'classic'): 'band_rock',
    ('punk_pop',        'rock'):    'band_rock',
    # Indie production (same instruments, indie pool)
    ('shoegaze',    'indie'): 'indie_alt',
    ('shoegaze',    'rock'):  'band_rock',
    ('indie_rock',  'indie'): 'indie_alt',
    ('art_rock',    'indie'): 'indie_alt',
    ('folk_rock',   'indie'): 'indie_alt',
    ('folk_rock',   'rock'):  'band_rock',
    # Acoustic / organic
    ('acoustic_pop',       'indie'): 'acoustic_minimal',
    ('acoustic_pop',       'pop'):   'acoustic_minimal',
    ('singer_songwriter',  'indie'): 'acoustic_minimal',
    ('singer_songwriter',  'rock'):  'acoustic_minimal',
    # Cinematic / classical
    ('cinematic_score', 'classic'): 'cinematic',
    ('cinematic_pop',   'indie'):   'cinematic',
    ('dream_pop',       'indie'):   'cinematic',
    # Latin urban — reggaeton / latin trap / dembow share a distinct rhythmic
    # identity (808-driven dembow pattern) that is structurally different from
    # EDM/synth-pop despite also using electronic production tools.
    # All Latin styles with a 'latin' genre context map to 'latin_urban'.
    ('reggaeton',        'latin'):  'latin_urban',
    ('latin_pop',        'latin'):  'latin_urban',
    ('latin_trap',       'latin'):  'latin_urban',
    ('dembow',           'latin'):  'latin_urban',
    ('regional_mexican', 'latin'):  'latin_urban',
    ('afrobeats',        'latin'):  'latin_urban',  # Afro-Latin crossover
}

# Maps production signature → ecosystem directly.
# 'cinematic' is intentionally absent: it requires downstream style-pool
# resolution to distinguish electronic downtempo from orchestral classical.
_PROD_SIG_ECOSYSTEM: Dict[str, str] = {
    'electronic_synth': 'electronic_synth',
    'disco_funk':        'electronic_synth',  # disco/funk = electronic territory
    'band_rock':         'rock_band',
    'acoustic_minimal':  'indie_alt',
    'trap_beats':        'hiphop_trap',
    'rnb_soul':          'rnb_soul',
    'indie_alt':         'indie_alt',
    # Latin urban: reggaeton / latin trap / dembow always map to afrobeats_world
    # regardless of the coarse production-feel value.
    'latin_urban':       'afrobeats_world',
}

# Maps coarse production-feel values to signature vocabulary for fallback.
_PROD_FEEL_TO_SIG: Dict[str, str] = {
    'electronic': 'electronic_synth',
    'trap':       'trap_beats',
    'band':       'band_rock',
    'acoustic':   'acoustic_minimal',
    'minimal':    'rnb_soul',
    'cinematic':  'cinematic',
    'mixed':      'mixed',
}

# ──────────────────────────────────────────────────────────────────────────────
# Last.fm tag → internal style family
# ──────────────────────────────────────────────────────────────────────────────
# Maps crowd-sourced Last.fm tag strings (lowercased) to the style family vocab
# used throughout the recommendation pipeline.  Only specific, unambiguous tags
# are included — broad labels like 'pop' or 'rock' are omitted here because
# they carry no production-level information and would dilute signal.
_TAG_STYLE_MAP: Dict[str, str] = {
    # ── Synth / electronic pop ──────────────────────────────────────────────
    'synth-pop':           'synth_pop',
    'synthpop':            'synth_pop',
    'synthwave':           'synth_pop',
    'synth pop':           'synth_pop',
    'synthwave pop':       'synth_pop',
    'electropop':          'synth_pop',
    'electro pop':         'synth_pop',
    'new wave':            'synth_pop',
    'retro pop':           'synth_pop',
    'retrowave':           'synth_pop',
    'indie electronic':    'synth_pop',   # electronic production, indie feel
    'future bass':         'synth_pop',   # melodic/synth-driven electronic
    'chillwave':           'synth_pop',   # atmospheric synth pop
    '80s':                 'synth_pop',   # strong production-era signal
    # ── Dance / disco / funk ────────────────────────────────────────────────
    'dance-pop':           'dance_pop',
    'dance pop':           'dance_pop',
    'disco':               'dance_pop',
    'funk':                'dance_pop',
    'nu-disco':            'dance_pop',
    'nu disco':            'dance_pop',
    'disco funk':          'dance_pop',
    'french house':        'house',       # specific dance-electronic sub-genre
    'electro house':       'house',
    # ── Pure electronic genres ──────────────────────────────────────────────
    'edm':                 'festival_edm',
    'electronic dance music': 'festival_edm',
    'big room':            'festival_edm',
    'progressive house':   'festival_edm',
    'house':               'house',
    'deep house':          'house',
    'tech house':          'house',
    'tropical house':      'house',
    'techno':              'techno',
    'trance':              'trance',
    'progressive trance':  'trance',
    'vocal trance':        'trance',
    'drum and bass':       'drum_bass',
    'drum & bass':         'drum_bass',
    'dnb':                 'drum_bass',
    'liquid dnb':          'drum_bass',
    'uk garage':           'uk_garage',
    '2-step':              'uk_garage',
    'idm':                 'idm',
    'intelligent dance music': 'idm',
    'electronica':         'idm',
    # ── Cinematic / ambient / trip-hop / chill ──────────────────────────────
    'ambient':             'ambient',
    'ambient electronic':  'ambient',
    'trip-hop':            'downtempo',
    'trip hop':            'downtempo',
    'downtempo':           'downtempo',
    'chillout':            'downtempo',
    'chill out':           'downtempo',
    'lo-fi':               'downtempo',
    'lo fi':               'downtempo',
    'lo-fi hip hop':       'downtempo',
    # ── R&B / soul ──────────────────────────────────────────────────────────
    'r&b':                 'alt_rnb',
    'rnb':                 'alt_rnb',
    'rhythm and blues':    'alt_rnb',
    'alternative r&b':     'alt_rnb',
    'alt r&b':             'alt_rnb',
    'contemporary r&b':    'smooth_rnb',
    'smooth r&b':          'smooth_rnb',
    'soul':                'soul',
    'soul music':          'soul',
    'neo soul':            'neo_soul',
    'neo-soul':            'neo_soul',
    'funk soul':           'neo_soul',
    'pop soul':            'soul',
    # ── Hip-hop / trap ──────────────────────────────────────────────────────
    'hip-hop':             'lyrical_rap',
    'hip hop':             'lyrical_rap',
    'rap':                 'lyrical_rap',
    'conscious hip-hop':   'lyrical_rap',
    'conscious hip hop':   'lyrical_rap',
    'alternative hip-hop': 'lyrical_rap',
    'west coast hip-hop':  'lyrical_rap',
    'east coast hip-hop':  'lyrical_rap',
    'jazz hop':            'lyrical_rap',
    'trap':                'trap',
    'trap music':          'trap',
    'melodic rap':         'melodic_rap',
    'melodic trap':        'melodic_rap',
    # ── Rock / indie rock ───────────────────────────────────────────────────
    'indie rock':          'indie_rock',
    'alternative rock':    'alt_rock',
    'alt-rock':            'alt_rock',
    'post-rock':           'post_rock',
    'post rock':           'post_rock',
    'shoegaze':            'shoegaze',
    'art rock':            'art_rock',
    'punk rock':           'punk_pop',
    'pop punk':            'punk_pop',
    'post-punk':           'art_rock',
    'post punk':           'art_rock',
    'britpop':             'indie_rock',
    'post-britpop':        'indie_rock',
    'math rock':           'post_rock',
    'glam rock':           'art_rock',
    # ── Indie pop crossover ─────────────────────────────────────────────────
    'indie pop':           'indie_rock',
    'dream pop':           'dream_pop',
    'dark pop':            'cinematic_pop',
    'alt pop':             'cinematic_pop',
    'art pop':             'cinematic_pop',
    'bedroom pop':         'indie_rock',
    'pop rock':            'indie_rock',
    'power pop':           'indie_rock',
    # ── Acoustic / folk / singer-songwriter ─────────────────────────────────
    'acoustic':            'acoustic_pop',
    'acoustic pop':        'acoustic_pop',
    'folk':                'singer_songwriter',
    'indie folk':          'singer_songwriter',
    'folk rock':           'folk_rock',
    'singer-songwriter':   'singer_songwriter',
    'soft rock':           'acoustic_pop',
    # ── World / Afrobeats ───────────────────────────────────────────────────
    'afrobeats':           'afrobeats',
    'afrobeat':            'afrobeats',
    'afro pop':            'afrobeats',
    'afropop':             'afrobeats',
    'amapiano':            'amapiano',
    'afro fusion':         'afro_fusion',
    # ── Latin urban ──────────────────────────────────────────────────────────
    'reggaeton':           'reggaeton',
    'latin':               'latin_pop',
    'latin pop':           'latin_pop',
    'latin urban':         'reggaeton',
    'urbano latino':       'reggaeton',
    'latin trap':          'reggaeton',    # latin trap = reggaeton family
    'dembow':              'reggaeton',
    'perreo':              'reggaeton',
    'trap latino':         'reggaeton',
    'musica urbana':       'reggaeton',
    'spanish':             'latin_pop',    # spanish-language signal
    'tropical':            'latin_pop',
    'bachata':             'latin_pop',
    'salsa':               'latin_pop',
    'cumbia':              'latin_pop',
    'corridos tumbados':   'regional_mexican',
    'regional mexicano':   'regional_mexican',
    # ── Classical / cinematic ───────────────────────────────────────────────
    'classical':           'cinematic_score',
    'orchestral':          'cinematic_score',
    'film score':          'cinematic_score',
    'neoclassical':        'cinematic_score',
    'modern classical':    'cinematic_score',
    'neo-classical':       'cinematic_score',
}

# Tags too broad to carry meaningful production information on their own.
# Multi-word or specific tags ('synth-pop', 'trip-hop', 'neo soul') dominate;
# these single-word genre labels are only used when no specific tag matches.
_BROAD_TAGS: frozenset = frozenset({'rock', 'pop', 'electronic', 'indie'})


def _classify_production_signature(style: str, genre: str) -> str:
    """
    Classify the source song's production signature using style + genre.

    More granular than the production-feel taxonomy used for scoring.
    Mood is NEVER consulted — this is a structural, sonic-identity assignment.

    Lookup order:
      1. (style, genre) → _PROD_SIGNATURE_MAP  (most specific)
      2. style alone    → _PROD_FROM_STYLE feel → _PROD_FEEL_TO_SIG
      3. genre alone    → _PROD_FROM_GENRE feel → _PROD_FEEL_TO_SIG
      4. 'mixed'        (no signal strong enough to classify)
    """
    if style and style != 'unknown':
        sig = _PROD_SIGNATURE_MAP.get((style, genre))
        if sig:
            return sig
        feel = _PROD_FROM_STYLE.get(style)
        if feel:
            return _PROD_FEEL_TO_SIG.get(feel, 'mixed')

    feel = _PROD_FROM_GENRE.get(genre)
    if feel:
        return _PROD_FEEL_TO_SIG.get(feel, 'mixed')

    return 'mixed'


def _infer_ecosystem(production: str, style: str, genre: str,
                     prod_sig: str = '') -> str:
    """
    Derive the source song's musical ecosystem from production + style,
    with genre as final fallback.

    When prod_sig is provided (from _classify_production_signature), it is
    checked first against _PROD_SIG_ECOSYSTEM for a direct, unambiguous answer.
    Signatures that are deliberately absent ('cinematic', 'mixed') fall through
    to the existing production-feel × style-pool resolution below.

    Lookup order:
      1. prod_sig → _PROD_SIG_ECOSYSTEM   (unambiguous direct mapping)
      2. (production, style_pool) → _PROD_POOL_ECOSYSTEM
      3. (production, genre)      → _PROD_POOL_ECOSYSTEM
      4. (production, '')         → _PROD_POOL_ECOSYSTEM
      5. style_pool → POOL_ECOSYSTEM
      6. genre → POOL_ECOSYSTEM
    """
    if prod_sig:
        eco = _PROD_SIG_ECOSYSTEM.get(prod_sig)
        if eco:
            return eco
        # 'cinematic' and 'mixed' intentionally fall through to style resolution

    style_pool = STYLE_GENRE_AFFINITY.get(style, '')

    eco = (_PROD_POOL_ECOSYSTEM.get((production, style_pool)) or
           _PROD_POOL_ECOSYSTEM.get((production, genre)) or
           _PROD_POOL_ECOSYSTEM.get((production, '')))
    if eco:
        return eco

    if style_pool:
        eco = POOL_ECOSYSTEM.get(style_pool)
        if eco:
            return eco

    return POOL_ECOSYSTEM.get(genre, 'pop_synth')


def _get_song_style(artist: str, song: str) -> str:
    """
    Return style/subgenre for a specific song.
    Priority: SONG_STYLE_OVERRIDE → ARTIST_STYLE → 'unknown'
    No external calls; O(1) lookup.
    """
    a_key = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s.*', '', artist.lower().strip(),
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


def _infer_production(style: str, genre: str,
                       mood: str = '', energy: str = '') -> str:
    """
    Infer song production feel from its style/subgenre.

    Base: style → _PROD_FROM_STYLE (precise). Unknown style → 'mixed'.

    Song-level softening (applied only when mood+energy are supplied, i.e.
    for the SOURCE song — never for candidates):
      • electronic base + sad/relaxed/romantic + low energy → 'cinematic'
        Slow melancholic tracks by electronic/synth-pop artists feel cinematic,
        not like high-BPM EDM.  Same artist, different songs → different profiles.
      • trap base + sad/romantic + low/mid energy → 'minimal'
        Melodic/emotional rap tracks feel stripped-down, not hard trap.

    This is the song-first mechanism: the same artist's upbeat and gentle
    tracks produce different production profiles without any per-song data.

    Returns one of: electronic | acoustic | band | trap | cinematic | minimal | mixed
    """
    if style and style != 'unknown':
        prod = _PROD_FROM_STYLE.get(style)
        base = prod if prod else 'mixed'
    else:
        base = 'mixed'

    # Song-level softening when mood+energy are known (source song only)
    if mood and energy:
        if base == 'electronic' and energy == 'low' and mood in ('sad', 'relaxed', 'romantic'):
            return 'cinematic'
        if base == 'trap' and energy in ('low', 'mid') and mood in ('sad', 'romantic'):
            return 'minimal'

    return base


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
    clean = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s.*', '', key, flags=re.IGNORECASE).strip()
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
    clean = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s.*', '', key, flags=re.IGNORECASE).strip()
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


@lru_cache(maxsize=512)
def _fetch_track_tags(artist: str, song: str) -> tuple:
    """
    Fetch Last.fm crowd-sourced top tags for a specific track.

    Returns a tuple of (tag_name_lower, count) pairs sorted by count
    descending, ready for _resolve_style_from_tags.

    Song-level: tags reflect THIS track's sonic character, not the artist's
    genre label.  For example 'Blinding Lights' returns ('synth-pop', 100),
    ('new wave', 82), ('80s', 60) … not just 'r&b' because The Weeknd is
    classified as R&B.

    Cached with lru_cache(512) so repeated identical queries are free.
    Returns () on any network failure or missing API key — callers must
    handle the empty case gracefully.
    """
    api_key = os.environ.get('LASTFM_API_KEY', '')
    if not api_key:
        return ()
    try:
        r = requests.get(
            'https://ws.audioscrobbler.com/2.0/',
            params={
                'method':      'track.getTopTags',
                'artist':      artist,
                'track':       song,
                'api_key':     api_key,
                'format':      'json',
                'autocorrect': '1',
            },
            timeout=4,
        )
        if r.status_code == 200:
            raw = r.json().get('toptags', {}).get('tag', [])
            return tuple(
                (t['name'].lower().strip(), int(t.get('count', 0)))
                for t in raw if t.get('name')
            )
    except Exception:
        pass
    return ()


def _resolve_style_from_tags(tag_pairs: tuple) -> Optional[str]:
    """
    Vote-tally Last.fm (tag, count) pairs into a single internal style family.

    Algorithm:
      • Each tag mapped by _TAG_STYLE_MAP contributes a weighted vote equal to
        (count / max_count) * specificity_multiplier.
      • Multi-word or hyphenated tags ('synth-pop', 'nu disco', 'alternative r&b')
        receive a 1.3× specificity boost because they encode more precise
        production information than single-word labels.
      • Tags in _BROAD_TAGS ('pop', 'rock', 'electronic', 'indie') are skipped
        in the first pass; they are only used if no specific tag matches at all.
      • The style with the highest total weighted vote wins.
      • Two thresholds control override confidence:
          – strong single:  a specific multi-word tag whose raw weight ≥ 0.50
            (i.e. at least 50 % of the top-tag listener count) overrides
            artist_style even without cumulative consensus.
          – cumulative:     total votes for the winning style ≥ 0.25 (as before).
        Either condition is sufficient.

    Returns the winning style string, or None if confidence is too low.
    """
    if not tag_pairs:
        return None

    max_count = max(c for _, c in tag_pairs) or 1

    votes: Dict[str, float] = {}
    top_specific_weight: float = 0.0   # highest raw weight seen for any specific tag

    for tag, count in tag_pairs[:15]:
        style = _TAG_STYLE_MAP.get(tag)
        if not style:
            continue
        if tag in _BROAD_TAGS:
            continue   # skip broad single-word tags; specific ones dominate

        raw_weight = count / max_count
        # Multi-word or hyphenated tags carry more production specificity
        is_specific = (' ' in tag or '-' in tag)
        weight = raw_weight * 1.3 if is_specific else raw_weight

        if is_specific and raw_weight > top_specific_weight:
            top_specific_weight = raw_weight

        votes[style] = votes.get(style, 0.0) + weight

    # If no specific tags matched, try broad tags as last resort
    if not votes:
        for tag, count in tag_pairs[:15]:
            style = _TAG_STYLE_MAP.get(tag)
            if style:
                weight = count / max_count
                votes[style] = votes.get(style, 0.0) + weight

    if not votes:
        return None

    best_style = max(votes, key=lambda s: votes[s])
    best_votes  = votes[best_style]

    # Accept override if cumulative confidence OR a single strong specific tag
    strong_single = (top_specific_weight >= 0.50)
    if best_votes < 0.25 and not strong_single:
        return None

    logger.debug(
        f"[TAG] style resolved: {best_style} "
        f"(votes={votes}, top_specific_weight={top_specific_weight:.2f})"
    )
    return best_style


def _build_song_profile(artist: str, song: str, handler_mood: str, genre: str) -> Dict:
    """
    Build a song-first profile dict.

    Primary signals (derived from the song itself):
      mood       — from title keywords + handler hint
      energy     — from title keywords, with mood as fallback
      production — from style/subgenre mapping
      style      — Last.fm track tags (song-level) → SONG_STYLE_OVERRIDE
                   → ARTIST_STYLE (artist-level, weakest signal)

    Secondary signals (artist-level, kept as weak context):
      vocal, era — from ARTIST_PROFILE
    """
    ap           = _get_artist_profile(artist)
    mood         = _infer_mood_from_title(song, genre, handler_mood)

    # Style: song-level Last.fm tags override artist-level lookup.
    # _fetch_track_tags() is cached; returns () when API key is absent or call
    # fails, so the pipeline degrades gracefully to artist-level style.
    artist_style = _get_song_style(artist, song)
    tag_style    = _resolve_style_from_tags(_fetch_track_tags(artist, song))
    style        = tag_style if tag_style else artist_style

    energy     = _infer_energy(song, mood, genre)
    production = _infer_production(style, genre, mood, energy)  # song-aware softening
    # Production signature: mood-free, style+genre-driven, finer than production feel.
    # Used only for ecosystem assignment — does not affect scoring compatibility.
    prod_sig   = _classify_production_signature(style, genre)

    if tag_style:
        raw_tags   = _fetch_track_tags(artist, song)          # already cached
        top_tags   = [t for t, _ in raw_tags[:5]]
        final_eco  = _infer_ecosystem(production, style, genre, prod_sig)
        logger.info(
            f"[IDENTITY] {artist} — {song}: "
            f"tag_style={tag_style!r} overrides artist_style={artist_style!r} | "
            f"top_tags={top_tags} | "
            f"production={production!r} ecosystem={final_eco!r}"
        )

    return {
        'genre':      genre,
        'mood':       mood,
        'style':      style,
        'energy':     energy,
        'production': production,
        'prod_sig':   prod_sig,   # mood-free structural identity; used to gate pool expansion
        'vocal':      ap.get('vocal', 'male'),
        'era':        ap.get('era', 'modern'),
        'ecosystem':  _infer_ecosystem(production, style, genre, prod_sig),
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

    # ── Ecosystem alignment score ──────────────────────────────────────────────
    # Explicit structural signal: how well does the candidate's broad musical
    # family align with the source song's ecosystem?  Three tiers:
    #   100 — same ecosystem (primary domain)
    #    60 — adjacent ecosystem (musically neighbouring, e.g. rnb↔pop)
    #     0 — non-adjacent (different musical world)
    # This prevents mood-only coincidences from elevating candidates that are
    # fundamentally outside the source song's musical ecosystem, and ensures
    # style + production + ecosystem together clearly outweigh mood alone.
    source_ecosystem  = source.get('ecosystem', POOL_ECOSYSTEM.get(source['genre'], 'pop_synth'))
    adjacent_ecos     = ECOSYSTEM_ADJACENT.get(source_ecosystem, frozenset({source_ecosystem}))
    c_ecosystem       = POOL_ECOSYSTEM.get(candidate_genre, 'pop_synth')

    if c_ecosystem == source_ecosystem:
        ecosystem_score = 100.0
    elif c_ecosystem in adjacent_ecos:
        ecosystem_score = 70.0
    else:
        # Soft floor — don't zero-out candidates that Last.fm says are genuinely
        # similar.  A 35/100 ecosystem score still meaningfully penalises
        # cross-ecosystem candidates relative to in-ecosystem ones.
        ecosystem_score = 35.0

    # Weight distribution (v4 — ecosystem-aware):
    #   20% mood           primary emotional tone of the song
    #   20% style          subgenre family
    #   18% energy         level inferred from the song
    #   15% production     sonic texture
    #   11% genre          broad pool match (reduced: ecosystem now carries 8%)
    #    8% ecosystem      musical-family alignment — guards against cross-genre
    #    5% vocal          artist-level tiebreaker
    #    3% era            artist-level tiebreaker
    # Song-first signals (mood + energy + production = 53%) outweigh
    # identity signals (style + genre + ecosystem + vocal + era = 47%).
    # Within identity signals, ecosystem (8%) explicitly bounds cross-genre
    # drift that style + genre scores alone cannot prevent.
    score = (
        0.20 * mood_score       +
        0.20 * style_score      +
        0.18 * energy_score     +
        0.15 * production_score +
        0.11 * genre_score      +
        0.08 * ecosystem_score  +
        0.05 * vocal_score      +
        0.03 * era_score
    )

    # ── Constellation bonus — ecosystem-gated ─────────────────────────────────
    # Reward simultaneous alignment across all three core song-first dimensions.
    # Gated: bonus only applies when the candidate is already within the source
    # song's adjacent ecosystem — mood+energy coincidences cannot boost a
    # fundamentally unrelated candidate into the results.
    if c_ecosystem in adjacent_ecos:
        n_core = (int(mood_score >= 80) +
                  int(energy_score >= 72) +
                  int(production_score >= 75))
        if n_core == 3:
            score += 12.0   # all three core dimensions align
        elif n_core == 2:
            score += 5.0    # two of three align

    return score


def _generate_reason(candidate_artist: str, candidate_name: str,
                     candidate_genre: str, source: Dict,
                     existing_reason: str = '') -> str:
    """
    Generate a rich, context-specific reason string derived from the source song
    profile (style, production, mood, era).  Avoids generic fallbacks like
    'pop sound' — every phrase reflects a concrete dimension of the source song.

    Priority:
      1. Existing curated reason (kept when non-generic).
      2. Style match phrase  — most specific.
      3. Production + mood phrase — sonic texture.
      4. Genre + mood fallback.
    """
    if (existing_reason
            and existing_reason not in ('Trending on Apple Music Top 100', '')):
        return existing_reason

    src_style      = source.get('style', 'unknown')
    src_production = source.get('production', 'mixed')
    src_mood       = source.get('mood', '')
    src_era        = source.get('era', 'modern')

    c_mood = _infer_mood_from_title(candidate_name, candidate_genre, '')

    # ── Style → descriptive phrase ────────────────────────────────────────────
    _STYLE_PHRASES: Dict[str, str] = {
        # Electronic / synth
        'synthwave':         'retro synthwave atmosphere',
        'synth_pop':         'catchy synth-pop groove',
        'indie_electronic':  'indie-electronic texture',
        'nu_disco':          'nu-disco funk feel',
        'dark_electronic':   'dark electronic production',
        'edm':               'festival-ready electronic energy',
        'house':             'house-influenced groove',
        'ambient_electronic':'atmospheric electronic soundscape',
        # R&B / soul
        'alt_rnb':           'dark alt-R&B atmosphere',
        'dark_rnb':          'moody dark R&B feel',
        'neo_soul':          'neo-soul warmth',
        'classic_soul':      'classic soul depth',
        'bedroom_pop':       'lo-fi bedroom-pop intimacy',
        # Hip-hop
        'trap':              'modern trap production',
        'drill':             'drill-influenced production',
        'lo_fi_hiphop':      'lo-fi hip-hop chill',
        'conscious_hiphop':  'lyric-driven hip-hop feel',
        'boom_bap':          'boom-bap hip-hop energy',
        # Rock / indie
        'indie_rock':        'indie guitar-driven sound',
        'psychedelic_rock':  'psychedelic guitar atmosphere',
        'alternative_rock':  'alternative rock edge',
        'post_punk':         'post-punk intensity',
        'shoegaze':          'hazy shoegaze texture',
        'dream_pop':         'ethereal dream-pop feel',
        'folk_pop':          'acoustic folk-pop warmth',
        'indie_folk':        'introspective indie-folk sound',
        # Pop
        'power_pop':         'anthemic pop energy',
        'dance_pop':         'danceable pop production',
        'art_pop':           'experimental art-pop sensibility',
        # Latin / world
        'latin_pop':         'Latin pop groove',
        'reggaeton':         'reggaeton-driven rhythm',
        'afrobeats':         'Afrobeats pulse',
        'afropop':           'Afropop energy',
        'dancehall':         'dancehall swing',
        'bossa_nova':        'bossa nova elegance',
        # Classical / cinematic
        'classical':         'orchestral depth',
        'cinematic':         'cinematic atmosphere',
        'ambient':           'ambient texture',
    }

    # ── Production → sonic description ───────────────────────────────────────
    _PROD_PHRASES: Dict[str, str] = {
        'electronic': 'electronic production',
        'trap':       'trap-influenced production',
        'acoustic':   'acoustic, stripped-back feel',
        'band':       'live band energy',
        'cinematic':  'cinematic, atmospheric production',
        'minimal':    'minimal, intimate production',
        'mixed':      'layered production',
    }

    # ── Era → contextual marker ───────────────────────────────────────────────
    _ERA_PHRASES: Dict[str, str] = {
        '80s':    '80s-influenced aesthetic',
        '90s':    '90s R&B feel',
        '2000s':  'early 2000s sound',
        '2010s':  '2010s indie pop energy',
        'modern': 'contemporary sound',
        'classic':'classic, timeless feel',
    }

    # ── Mood → adjective ──────────────────────────────────────────────────────
    _MOOD_ADJ: Dict[str, str] = {
        'sad':       'melancholic', 'romantic': 'romantic', 'energetic': 'energetic',
        'happy':     'upbeat',     'chill':    'laid-back',
    }

    style_phrase = _STYLE_PHRASES.get(src_style, '')
    prod_phrase  = _PROD_PHRASES.get(src_production, '')
    era_phrase   = _ERA_PHRASES.get(src_era, '') if src_era not in ('modern', '') else ''
    mood_adj     = _MOOD_ADJ.get(src_mood, '')
    mood_match   = (c_mood == src_mood)

    # Priority 1: if we have a specific style phrase, build around it
    if style_phrase:
        if mood_match and mood_adj:
            return f"{mood_adj} {style_phrase}"
        if era_phrase:
            return f"{style_phrase} with {era_phrase}"
        return style_phrase

    # Priority 2: production + mood context
    if prod_phrase:
        if mood_match and mood_adj:
            return f"{mood_adj} {prod_phrase}"
        if era_phrase:
            return f"{prod_phrase} — {era_phrase}"
        return prod_phrase

    # Priority 3: genre + mood fallback (more specific than before)
    _GENRE_PHRASES: Dict[str, str] = {
        'afrobeats': 'Afrobeats rhythm', 'pop':    'polished pop feel',
        'rnb':       'R&B warmth',        'hiphop': 'hip-hop energy',
        'rock':      'rock edge',         'latin':  'Latin groove',
        'classic':   'timeless sound',   'indie':  'indie sensibility',
    }
    genre_phrase = _GENRE_PHRASES.get(candidate_genre, 'similar sonic feel')
    if mood_adj and mood_match:
        return f"{mood_adj} {genre_phrase}"
    return genre_phrase


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

    # ── Ecosystem filter ─────────────────────────────────────────────────────
    # Discard Apple Music candidates whose artist genre maps to an ecosystem
    # that is completely outside the source song's neighbourhood.  This prevents
    # chart-dominant genres (e.g. hip-hop or country) from flooding the quality
    # pool simply because their mood/energy scores are adequate.
    source_eco   = source_profile.get('ecosystem', 'pop_synth')
    adj_ecos     = ECOSYSTEM_ADJACENT.get(source_eco, frozenset({source_eco}))
    pre_filter   = len(scored)
    scored = [(s, c, g) for s, c, g in scored
              if POOL_ECOSYSTEM.get(g, 'pop_synth') in adj_ecos]
    if len(scored) < pre_filter:
        logger.info(f"[REC] Apple ecosystem filter ({source_eco}): "
                    f"{pre_filter - len(scored)} FAR-ecosystem candidates removed "
                    f"({len(scored)} remain)")

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

    # Determine the source song's ecosystem and its adjacent set first —
    # the pool seeding logic below uses adjacent_ecos to decide whether
    # the artist-level genre pool belongs in the candidate neighbourhood.
    source_ecosystem = source_profile.get('ecosystem',
                           POOL_ECOSYSTEM.get(genre, 'pop_synth'))
    adjacent_ecos    = ECOSYSTEM_ADJACENT.get(source_ecosystem,
                           frozenset({source_ecosystem}))

    # ── Style-first pool seeding ────────────────────────────────────────────
    # Use the style's genre pool as the primary seed when style is known.
    # This prevents the artist-level genre (e.g. 'rnb' for The Weeknd) from
    # contaminating the pool when the track's production identity (e.g. synth_pop)
    # points to a completely different sonic territory.
    # The original genre is added back only when its ecosystem is adjacent to the
    # source song's ecosystem — keeping it as a secondary option, not the seed.
    style_genre = STYLE_GENRE_AFFINITY.get(source_style)
    if style_genre:
        pool_genres: set = {style_genre}
        if genre != style_genre:
            genre_eco = POOL_ECOSYSTEM.get(genre, 'pop_synth')
            if genre_eco in adjacent_ecos:
                pool_genres.add(genre)
                logger.info(f"[REC] style='{source_style}' seeds '{style_genre}'; "
                            f"genre='{genre}' re-added (ecosystem-adjacent)")
            else:
                logger.info(f"[REC] style='{source_style}' seeds '{style_genre}'; "
                            f"genre='{genre}' EXCLUDED (eco '{genre_eco}' ∉ adjacency)")
    else:
        pool_genres: set = {genre}

    # Expand with mood-related genres only when the style is unknown.
    # Known styles already route to the correct pool via STYLE_GENRE_AFFINITY;
    # mood expansion would add unrelated genre pools (e.g. rnb into dream_pop queries).
    # Ecosystem gate: only add pools whose ecosystem is within the adjacent set.
    if source_style == 'unknown':
        for rg in MOOD_GENRE_WEIGHTS.get(mood, ['pop']):
            if rg not in pool_genres:
                rg_eco = POOL_ECOSYSTEM.get(rg, source_ecosystem)
                if rg_eco in adjacent_ecos:
                    pool_genres.add(rg)
                    if len(pool_genres) >= 4:
                        break

    # ── Sonic pool hint: ecosystem-bounded song-first candidate expansion ──────
    # Add one further pool based on the song's combined mood × production
    # fingerprint, but only when the hinted pool belongs to the source song's
    # adjacent ecosystem.  This prevents a mood+production coincidence from
    # pulling in candidates from an unrelated musical world.
    #
    # Additional guard — prod_sig veto:
    # When the production signature indicates definitively electronic production
    # ('electronic_synth' / 'disco_funk'), block any sonic hint that would add a
    # non-electronic pool.  This prevents the mood-driven production *softening*
    # rule (e.g. electronic+romantic+low → cinematic) from leaking the resulting
    # softer feel into pool expansion and pulling in indie/folk candidates for
    # tracks that are structurally synth-pop or dance-electronic.
    _ELECTRONIC_SIGS: frozenset = frozenset({'electronic_synth', 'disco_funk'})
    source_prod = source_profile.get('production', 'mixed')
    prod_sig    = source_profile.get('prod_sig', '')
    sonic_hint  = SONIC_POOL_HINT.get((mood, source_prod))
    if sonic_hint and sonic_hint not in pool_genres:
        hint_eco         = POOL_ECOSYSTEM.get(sonic_hint, source_ecosystem)
        sig_blocks_hint  = (prod_sig in _ELECTRONIC_SIGS and
                            hint_eco not in ('electronic_synth',))
        if sig_blocks_hint:
            logger.info(f"[REC] sonic hint ({mood}×{source_prod}) → '{sonic_hint}' "
                        f"BLOCKED by prod_sig='{prod_sig}' (structural electronic identity)")
        elif hint_eco in adjacent_ecos:
            pool_genres.add(sonic_hint)
            logger.info(f"[REC] sonic hint ({mood}×{source_prod}) → '{sonic_hint}' "
                        f"[{hint_eco} ∈ {source_ecosystem} adjacency]")
        else:
            logger.info(f"[REC] sonic hint ({mood}×{source_prod}) → '{sonic_hint}' "
                        f"BLOCKED (ecosystem {hint_eco} ∉ {source_ecosystem} adjacency)")

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
# Last.fm track.getSimilar — primary candidate discovery
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _get_lastfm_similar_candidates(artist: str, song: str) -> tuple:
    """
    Call Last.fm track.getSimilar and return raw candidates as a frozen tuple
    of dicts (hashable for lru_cache).

    Returns up to 30 candidates sorted by Last.fm's own match score.
    Returns () when the API key is absent, the track is not found, or any
    network error occurs — callers must handle the empty case.
    """
    api_key = os.environ.get('LASTFM_API_KEY', '')
    if not api_key:
        logger.debug('[LASTFM] LASTFM_API_KEY not set — skipping getSimilar')
        return ()
    try:
        r = requests.get(
            'https://ws.audioscrobbler.com/2.0/',
            params={
                'method':      'track.getSimilar',
                'artist':      artist,
                'track':       song,
                'api_key':     api_key,
                'format':      'json',
                'limit':       30,
                'autocorrect': '1',
            },
            timeout=6,
        )
        data = r.json()

        if 'error' in data:
            logger.debug(f"[LASTFM] getSimilar error {data['error']}: {data.get('message','')}")
            return ()

        tracks = data.get('similartracks', {}).get('track', [])
        if not tracks:
            logger.info(f"[LASTFM] No similar tracks found for '{artist} - {song}'")
            return ()

        # Words in track names that signal low-quality / derivative results.
        _NOISE_WORDS = frozenset({
            'remix', 'cover', 'karaoke', 'instrumental', 'version',
            'tribute', 'acoustic', 'piano', 'mashup', 'medley', 'parody',
            'reprise', 'edit', 'remaster', 'remastered', 'live', 'demo',
            'bootleg', 'mix', 'extended', 'radio edit',
        })
        seed_artist_lower = artist.lower().strip()

        candidates = []
        for t in tracks:
            try:
                a_name = t['artist']['name'].strip()
                t_name = t['name'].strip()
                match  = float(t.get('match', 0))
                if not a_name or not t_name or match <= 0.02:
                    continue
                # Skip noise: derivative / low-quality versions
                t_lower = t_name.lower()
                if any(nw in t_lower.split() for nw in _NOISE_WORDS):
                    continue
                # Skip same artist as seed (user wants DIFFERENT artists)
                if a_name.lower().strip() == seed_artist_lower:
                    continue
                candidates.append({
                    'artist':        a_name,
                    'name':          t_name,
                    'reason':        '',   # generated later
                    'lastfm_match':  match,
                })
            except (KeyError, ValueError, TypeError):
                continue

        logger.info(
            f"[LASTFM] getSimilar: {len(candidates)} candidates "
            f"for '{artist} - {song}'"
        )
        # Return as tuple of frozensets so lru_cache can hash it
        return tuple(candidates)

    except Exception as e:
        logger.debug(f"[LASTFM] getSimilar network error: {e}")
        return ()


def _get_lastfm_recommendations(artist: str, song: str,
                                 source_profile: Dict) -> Optional[List[Dict]]:
    """
    Score + rank Last.fm similar tracks by vibe similarity to the source profile.

    Scoring formula (v2 — listener-graph-first):
        blended = lastfm_match * 65 + internal_score * 35

    Last.fm match (0-1) is the primary signal because it represents real listener
    co-occurrence across millions of plays — the most direct evidence that two
    songs belong in the same listening session.  Internal vibe score (0-100)
    acts as a coherence filter: it nudges the ranking toward candidates that
    share the same sonic fingerprint (mood, style, energy, production) without
    overriding the listener graph.

    Ecosystem compatibility is now a soft multiplier applied after scoring rather
    than a hard gate, so Last.fm neighbors from adjacent musical worlds are
    retained but ranked below in-ecosystem candidates:
        same ecosystem  → 1.00× (no penalty)
        adjacent        → 0.90× (mild discount)
        outside         → 0.65× (meaningful penalty, but not excluded)

    Returns None when fewer than 3 scored candidates are available, signalling
    that the caller should fall back to the curated pool.
    """
    raw = _get_lastfm_similar_candidates(artist, song)
    if not raw:
        return None

    source_eco = source_profile.get('ecosystem', 'pop_synth')
    adj_ecos   = ECOSYSTEM_ADJACENT.get(source_eco, frozenset({source_eco}))

    # Normalise source artist name for same-artist filtering.
    # Last.fm sometimes returns featured-artist strings like "The Weeknd, Daft Punk"
    # so we match by checking whether the source artist name is a substring of
    # the candidate artist string (case-insensitive).
    source_artist_lower = artist.lower()

    scored = []
    for c in raw:
        # Skip any track that is by the source artist (including featuring variants)
        if source_artist_lower in c['artist'].lower():
            continue

        c_genre = _detect_genre_fast(c['artist'])
        c_eco   = POOL_ECOSYSTEM.get(c_genre, 'pop_synth')

        internal = _score_candidate(c['artist'], c['name'], c_genre, source_profile)
        # Primary signal: Last.fm listener overlap (0-1 → up to 65 pts)
        # Refinement signal: internal vibe coherence (0-100 → up to 35 pts)
        blended = c['lastfm_match'] * 65 + internal * 0.35

        # Soft ecosystem multiplier — keeps cross-ecosystem Last.fm neighbors but
        # rewards in-ecosystem candidates in ranking.
        if c_eco == source_eco:
            eco_mult = 1.00
        elif c_eco in adj_ecos:
            eco_mult = 0.90
        else:
            eco_mult = 0.65

        blended *= eco_mult
        scored.append((blended, c, c_genre))

    if len(scored) < 3:
        logger.info(
            f"[LASTFM] Only {len(scored)} candidates for '{artist} - {song}' — "
            "falling back to curated"
        )
        return None

    scored.sort(key=lambda x: x[0], reverse=True)

    # Jitter top-12 pool for freshness, then deduplicate by artist
    top_pool = scored[:12]
    jittered = [(s + random.uniform(-1.5, 1.5), c, g) for s, c, g in top_pool]
    jittered.sort(key=lambda x: x[0], reverse=True)

    result       = []
    seen_artists: set = set()
    for _, c, c_genre in jittered:
        ak = c['artist'].lower()
        if ak not in seen_artists and ak != artist.lower():
            seen_artists.add(ak)
            rec          = dict(c)
            rec['reason'] = _generate_reason(
                c['artist'], c['name'], c_genre, source_profile, ''
            )
            result.append(rec)
        if len(result) == 5:
            break

    # Safety pad from the broader scored list if we're still short
    if len(result) < 5:
        for _, c, c_genre in scored:
            ak = c['artist'].lower()
            if ak not in seen_artists and ak != artist.lower():
                seen_artists.add(ak)
                rec           = dict(c)
                rec['reason'] = _generate_reason(
                    c['artist'], c['name'], c_genre, source_profile, ''
                )
                result.append(rec)
            if len(result) == 5:
                break

    if len(result) < 3:
        return None

    logger.info(
        f"[LASTFM] Returning {len(result)} recommendations "
        f"for '{artist} - {song}'"
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Public API (unchanged signatures)
# ──────────────────────────────────────────────────────────────────────────────

def get_similar_songs(artist: str, song: str, mood: str) -> List[Dict]:
    """
    Return 5 recommended songs similar in vibe to the source.

    Candidate discovery priority (song-first architecture):
      1. Last.fm track.getSimilar  — live, listener-overlap similarity graph.
                                     Up to 30 candidates, scored + ecosystem-filtered.
                                     Used when ≥ 3 candidates pass the ecosystem gate.
      2. Curated pool              — static GENRE_RECOMMENDATIONS per genre.
                                     Deterministic, always available, ~15-20 per genre.
      3. Blend                     — when Last.fm returns 3-4 songs, curated fills the
                                     remaining slots (avoiding duplicate artists).

    Apple Music is NOT used in this path.  It remains active only in
    artist_service.py for /trending and /top chart features.
    """
    try:
        genre          = _detect_genre(artist, song, mood)
        source_profile = _build_song_profile(artist, song, mood, genre)
        logger.info(
            f"[REC] profile for '{artist} - {song}': "
            f"genre={source_profile['genre']} mood={source_profile['mood']} "
            f"style={source_profile.get('style','?')} "
            f"vocal={source_profile['vocal']} era={source_profile['era']}"
        )

        # ── 1. Last.fm similarity graph ──────────────────────────────────────
        lastfm_recs = _get_lastfm_recommendations(artist, song, source_profile)

        if lastfm_recs and len(lastfm_recs) >= 5:
            # Full Last.fm result set — return directly
            return lastfm_recs

        # ── 2. Curated pool ──────────────────────────────────────────────────
        logger.info(f"[REC] Curated (scored) for '{artist} - {song}'")
        curated = _get_curated_recommendations(artist, song, mood, source_profile)

        if not lastfm_recs:
            # No Last.fm data (key absent, track not found, or too few results)
            return curated

        # ── 3. Blend — Last.fm partial + curated fill ────────────────────────
        # Last.fm gave 3-4 songs; pad to 5 from the curated pool, no duplicates.
        merged       = list(lastfm_recs)
        seen_artists = {r['artist'].lower() for r in merged}
        for rec in curated:
            if rec['artist'].lower() not in seen_artists:
                seen_artists.add(rec['artist'].lower())
                merged.append(rec)
            if len(merged) == 5:
                break

        logger.info(
            f"[REC] Blend: {len(lastfm_recs)} Last.fm + "
            f"{len(merged) - len(lastfm_recs)} curated for '{artist} - {song}'"
        )
        return merged

    except Exception as e:
        logger.error(f"[REC] Error in get_similar_songs: {e}", exc_info=True)
        genre          = _detect_genre_fast(artist)
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

    lines = []
    for i, song in enumerate(recommendations, 1):
        emoji = ['🔥', '✨', '💫', '🎶', '⭐'][i - 1] if i <= 5 else '🎵'
        lines.append(f"{emoji} {song['artist']} — {song['name']}")

    body   = '\n'.join(lines)
    footer = (
        "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
        "🎤 /lyrics to see any song's lyrics\n"
        "📊 /analyze for deeper insights"
    )

    return header + body + footer
