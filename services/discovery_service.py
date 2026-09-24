"""Discovery service — local-first music discovery helpers for the Lyrics Master bot.

Design rule (hard requirement): every feature runs PRIMARILY on unlimited
local sources — curated pools, cached data, local computation.  Rate-limited /
quota'd APIs (OpenAI, Last.fm, lyrics providers, the Apple chart) are
OPTIONAL enhancement only: each is wrapped in try/except, given a hard
timeout where possible, backed by an in-memory cache, and every function
falls back to a good local answer when the API is limited, slow, or down.

Module import performs NO network I/O.  Every public function never raises:
on any failure it returns [] / {} / a safe default.

Exception to the local-first rule: mood mixes are LIVE-first by explicit
product direction — a 3-tier fresh system (fresh chart -> genre feeds /
term search -> listener favorites); the pool is fallback/shortfall only.
"""

import json
import logging
import random as _rng
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from services.recommendation_service import (
    get_similar_songs, ARTIST_GENRE_MAP,
    _MOOD_KEYWORDS, _MOOD_COMPAT, _GENRE_MOOD_DEFAULT,
)
from services.live_charts import (
    get_fresh_songs, get_fresh_entries, get_fresh_genre_feed,
    search_songs_by_term, _is_fresh,
)
from services.artist_service import (
    GENRE_TOP_SONGS,
    GENRE_ALIASES,
    RANDOM_SONGS_POOL,
    TRENDING_SONGS,
    APPLE_GENRE_MAP,
    _recent_random_picks,
    get_trending_songs,
    _get_live_genre_songs,
)
from services.quiz_service import get_quiz_songs

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Module-level in-memory caches (API results only — local pools need none)
# ──────────────────────────────────────────────────────────────────────────────
_THEME_CACHE: Dict[str, Dict] = {}        # normalized theme text -> interpret_theme result
_MOOD_LIVE_CACHE: Dict[str, List[Dict]] = {}   # "artist - song - mood" -> live similar songs
_EXTEND_LIVE_CACHE: Dict[str, List[Dict]] = {}  # same key shape, for get_extend_recs

_SIMILAR_TIMEOUT = 8  # seconds — a live call slower than this is treated as "down"


# ──────────────────────────────────────────────────────────────────────────────
# Moods
# ──────────────────────────────────────────────────────────────────────────────
MOOD_BUTTONS = [
    ('😊 Happy', 'happy'),
    ('⚡ Hyped', 'energetic'),
    ('😌 Chill', 'relaxed'),
    ('😢 Sad', 'sad'),
    ('💖 Romantic', 'romantic'),
    ('🎉 Party', 'party'),
    ('🎯 Focus', 'focus'),
]

# Free-text keywords -> canonical mood.  Checked longest-first so that e.g.
# "workout" beats "work" and "heartbreak" beats "heart".
_MOOD_KEYWORD_MAP: Dict[str, List[str]] = {
    'happy': ['happiness', 'joyful', 'cheerful', 'upbeat', 'feel good',
              'feeling good', 'good vibes', 'sunshine', 'uplifting',
              'positive', 'glad', 'delighted', 'merry', 'bright', 'sunny',
              'happy'],
    'energetic': ['hyped', 'pumped', 'workout', 'hype', 'energetic', 'energy',
                  'gym', 'running', 'adrenaline', 'intense', 'powerful', 'amped',
                  'angry', 'furious', 'rage', 'pissed off'],
    'relaxed': ['chill', 'chilling', 'calm', 'calming', 'relax', 'relaxed',
                'relaxing', 'mellow', 'lazy', 'cozy', 'unwind', 'sunday',
                'coffee', 'lofi', 'laid back', 'sleepy', 'tired', 'sleep',
                'bedtime'],
    'sad': ['heartbreak', 'heartbroken', 'depress', 'melancholy', 'loneliness',
            'breakup', 'broke up', 'crying', 'tears', 'lonely', 'sad', 'blue',
            'cry', 'miss', 'missing', 'pain', 'hurt', 'hurting', 'emotional'],
    'romantic': ['romantic', 'romance', 'valentine', 'wedding', 'anniversary',
                 'dating', 'loving', 'loved', 'crush', 'kiss', 'heart', 'love',
                 'date'],
    'party': ['celebration', 'celebrate', 'birthday', 'clubbing', 'dancing',
              'dance', 'party', 'club', 'fiesta', 'tonight', 'drunk', 'pregame'],
    'focus': ['concentrating', 'concentrate', 'studying', 'working', 'deep work',
              'homework', 'coding', 'office', 'reading', 'focus', 'study', 'work'],
}

# Flat (keyword, mood) list sorted by keyword length, longest first.
_MOOD_KEYWORDS_SORTED: List[Tuple[str, str]] = sorted(
    ((kw, mood) for mood, kws in _MOOD_KEYWORD_MAP.items() for kw in kws),
    key=lambda kv: len(kv[0]),
    reverse=True,
)

# Canonical mood -> Last.fm tag used as the LIVE primary source for mixes.
# (Last.fm tags are user-applied; these are the best-trafficked ones per mood.)
_MOOD_LASTFM_TAG: Dict[str, str] = {
    'happy': 'happy',
    'energetic': 'workout',
    'relaxed': 'chill',
    'sad': 'sad',
    'romantic': 'romantic',
    'party': 'party',
    'focus': 'study',
}
_MOOD_TAG_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}  # tag -> (ts, tracks)
_MOOD_TAG_TTL_SECS = 12 * 3600  # 12h — tag charts move slowly

# Canonical mood -> internal mood key used by the recommendation engine's
# mood inference (title keywords + genre defaults).
_MOOD_INTERNAL = {
    'happy': 'happy',
    'energetic': 'energetic',
    'relaxed': 'chill',
    'sad': 'sad',
    'romantic': 'romantic',
    'party': 'party',  # own keyword set — sharing 'energetic' made the two
    'focus': 'chill',  # mixes byte-identical (round-13 wild-test finding).
}


# Apple genre tags (from the live chart feeds) that honestly signal a mood.
# Conservative on purpose: a genre is listed only when it genuinely fits.
# Round-13: energetic/party and relaxed/focus each get DISJOINT slices —
# sharing genre sets made party==energetic and relaxed≈focus in the wild.
_MOOD_APPLE_GENRES = {
    'happy': {'Pop', 'Dance', 'Reggae'},
    'energetic': {'Electronic', 'Hip-Hop/Rap', 'K-Pop'},
    'relaxed': {'Jazz', 'Reggae', 'Acoustic', 'Singer/Songwriter'},
    'sad': set(),
    'romantic': {'R&B/Soul', 'Singer/Songwriter'},
    'party': {'Dance', 'House', 'Latin Urban', 'Afrobeats'},
    'focus': {'Classical', 'New Age', 'Ambient'},
}

# Tier-3 shortfall sources per mood: (iTunes RSS genre feeds, search terms).
# Only used when tiers 1+2 leave the mix short — calm moods especially,
# since this week's all-genres chart carries almost no calm music.
# Round-13: party/energetic get their own genre feeds too, now that their
# tier-2 slices are disjoint (a hip-hop-heavy chart starves party, a
# dance-heavy chart starves energetic).
_MOOD_TIER3 = {
    'relaxed': ([(11, 'Jazz'), (5, 'Classical')], ['chill', 'calm']),
    'focus': ([(5, 'Classical'), (11, 'Jazz')], []),
    'sad': ([], ['lonely', 'goodbye', 'heartbreak']),
    'happy': ([], ['happy']),
    'energetic': ([(18, 'Hip-Hop/Rap')], ['hype']),
    'party': ([(17, 'Dance')], ['party']),
    'romantic': ([], ['love']),
}

# Artist-name fragments that mark compilation/karaoke/AI-farm junk in
# search results — the user wants real artists, no AI-generated music.
_JUNK_ARTIST_BITS = ('various artists', 'karaoke', 'tribute', 'collection',
                     'hits ', 'sing along', 'chill out', 'relaxing')


def _title_has_mood_word(title: str, internal: str) -> bool:
    try:
        words = set(re.sub(r"[^a-z\s]", "", (title or '').lower()).split())
        return bool(_MOOD_KEYWORDS.get(internal, set()) & words)
    except Exception:
        return False


def _apple_genre_fits_mood(genres, mood: str) -> bool:
    try:
        return bool(set(genres or []) & _MOOD_APPLE_GENRES.get(mood, set()))
    except Exception:
        return False


# Title fragments that mark karaoke/AI-farm/sleep-aid junk — checked in
# _claim_pick so EVERY mix tier (chart keywords, genre feeds, iTunes
# search, Last.fm tags) rejects them. The user wants real artists only.
_JUNK_TITLE_BITS = ('karaoke', 'tribute', '8d audio', 'slowed + reverb',
                    'slowed', 'sped up', 'nightcore', '1 hour', '10 hours',
                    'sing along', 'sax solos', 'beats to relax/study to',
                    'lofi hip hop radio')


def _norm_title(t: str) -> str:
    """Normalize a song title for dedup: lowercase, drop bracketed extras
    ("(Remix)", "[Live]"), collapse whitespace."""
    t = re.sub(r'\s*[\(\[].*?[\)\]]', '', str(t or ''))
    return re.sub(r'\s+', ' ', t).strip().lower()


def _claim_pick(out: List[Dict], seen_keys: set, seen_artists: set,
                artist: str, name: str, source: str, why: str = '',
                seen_titles: Optional[set] = None) -> bool:
    """Append a pick if unseen; True when added.

    Dedupes on (artist, title) AND on title alone — the same song must not
    appear twice under slightly different artist credits ("Babydoll" by
    'Jamie Miller' vs 'Jamie Miller & Antonio Cipriano', round-13 finding).
    Also rejects karaoke/AI-farm/junk titles at this single choke point.
    """
    try:
        a = str(artist or '').strip()
        t = str(name or '').strip()
        if not a or not t:
            return False
        tl = t.lower()
        if any(j in a.lower() for j in _JUNK_ARTIST_BITS):
            return False
        if any(j in tl for j in _JUNK_TITLE_BITS):
            return False
        key = (a.lower(), t.lower())
        if key in seen_keys or a.lower() in seen_artists:
            return False
        if seen_titles is not None:
            nt = _norm_title(t)
            if nt and nt in seen_titles:
                return False
            seen_titles.add(nt)
        seen_keys.add(key)
        seen_artists.add(a.lower())
        out.append({'artist': a, 'name': t, 'source': source, 'why': why})
        return True
    except Exception:
        return False


def _tier12_picks(entries: List[Dict], mood: str, internal: str, want: int,
                  seen_keys: set, seen_artists: set,
                  seen_titles: Optional[set] = None) -> List[Dict]:
    """Tier 1 (title keyword) then tier 2 (Apple genre) from fresh entries."""
    out: List[Dict] = []
    try:
        calm = mood in ('relaxed', 'focus')
        for e in entries:  # tier 1 — title carries a real mood word
            if len(out) >= want:
                break
            if calm and _too_fast_for_calm(e.get('song', '')):
                continue
            if _title_has_mood_word(e.get('song', ''), internal):
                _claim_pick(out, seen_keys, seen_artists,
                            e.get('artist'), e.get('song'), 'fresh', 'keyword',
                            seen_titles)
        for e in entries:  # tier 2 — Apple's own genre tag fits the mood
            if len(out) >= want:
                break
            if calm and _too_fast_for_calm(e.get('song', '')):
                continue
            if _apple_genre_fits_mood(e.get('genres'), mood):
                _claim_pick(out, seen_keys, seen_artists,
                            e.get('artist'), e.get('song'), 'fresh', 'genre',
                            seen_titles)
    except Exception:
        pass
    return out


def _too_fast_for_calm(title: str) -> bool:
    """BPM markers are explicit tempo metadata — honor them for calm moods."""
    try:
        m = re.search(r'\(\s*(\d{2,3})\s*bpm', str(title or ''), re.I)
        return bool(m and int(m.group(1)) >= 150)
    except Exception:
        return False


def _tier3_picks(mood: str, internal: str, want: int,
                 seen_keys: set, seen_artists: set,
                 seen_titles: Optional[set] = None) -> List[Dict]:
    """Shortfall tier: genre feeds + iTunes term search, still fresh-only.

    Genre RSS feeds are curated charts (no AI farms); search results get
    the junk/AI-farm guards.  Every candidate must still match the mood
    by keyword or genre — no guessing.  Never raises.
    """
    out: List[Dict] = []
    try:
        feeds, terms = _MOOD_TIER3.get(mood, ([], []))
        for gid, gname in feeds:
            if len(out) >= want:
                break
            feed = _tier12_picks(get_fresh_genre_feed(gid, gname),
                                 mood, internal, want - len(out),
                                 seen_keys, seen_artists, seen_titles)
            out += feed
        for term in terms:
            if len(out) >= want:
                break
            for e in search_songs_by_term(term):
                if len(out) >= want:
                    break
                a = str(e.get('artist') or '').strip()
                t = str(e.get('song') or '').strip()
                if not a or not t:
                    continue
                if any(j in a.lower() for j in _JUNK_ARTIST_BITS):
                    continue
                if a.islower():
                    continue  # AI-farm guard
                if not _is_fresh(e, 24):
                    continue
                if not re.search(r'\b' + re.escape(term) + r'\b', t, re.I):
                    continue  # term must be a real word in the title
                if _title_has_mood_word(t, internal):
                    _claim_pick(out, seen_keys, seen_artists, a, t,
                                'fresh', 'search', seen_titles)
    except Exception:
        pass
    return out


def normalize_mood(text: str) -> Optional[str]:
    """Map free text to a canonical mood key from MOOD_BUTTONS, or None."""
    try:
        t = (text or '').lower()
        if not t.strip():
            return None
        # "unhappy" contains "happy" — catch the negation first.
        if re.search(r'\bunhappy\b', t):
            return 'sad'
        for kw, mood in _MOOD_KEYWORDS_SORTED:
            if kw in t:
                return mood
        return None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MOOD_SONG_POOLS — the PRIMARY (local, unlimited) source for mood mixes.
# 7 moods × 15 well-known songs, each with a real one-line reason.
# ──────────────────────────────────────────────────────────────────────────────
MOOD_SONG_POOLS: Dict[str, List[Dict]] = {
    'happy': [
        {'artist': 'Pharrell Williams', 'song': 'Happy',
         'reason': 'Pure joy in song form — impossible not to smile'},
        {'artist': 'ABBA', 'song': 'Dancing Queen',
         'reason': 'Timeless feel-good anthem, young and sweet'},
        {'artist': 'Katrina and the Waves', 'song': 'Walking on Sunshine',
         'reason': 'Sunshine pop at its brightest and bounciest'},
        {'artist': 'Bobby McFerrin', 'song': "Don't Worry Be Happy",
         'reason': 'The original good-vibes prescription'},
        {'artist': 'Cyndi Lauper', 'song': 'Girls Just Want to Have Fun',
         'reason': 'Playful 80s pop that never gets old'},
        {'artist': 'The Beach Boys', 'song': 'Good Vibrations',
         'reason': 'Good vibrations, exactly as promised'},
        {'artist': 'Stevie Wonder', 'song': 'Sir Duke',
         'reason': 'A brass-powered celebration of music itself'},
        {'artist': 'Earth, Wind & Fire', 'song': 'September',
         'reason': 'Do you remember? Instant dancefloor happiness'},
        {'artist': 'Whitney Houston', 'song': 'I Wanna Dance with Somebody',
         'reason': 'Pure 80s euphoria in every chorus'},
        {'artist': 'Queen', 'song': "Don't Stop Me Now",
         'reason': 'Freddie at his most unstoppable and joyful'},
        {'artist': 'Outkast', 'song': 'Hey Ya!',
         'reason': 'Funk-pop sugar rush, shake it like a Polaroid'},
        {'artist': 'The Beatles', 'song': 'Here Comes the Sun',
         'reason': 'George Harrison bottling a spring morning'},
        {'artist': 'Sister Sledge', 'song': 'We Are Family',
         'reason': 'Disco warmth about togetherness'},
        {'artist': 'Mark Ronson', 'song': 'Uptown Funk',
         'reason': 'Bruno Mars swagger over a monster groove'},
        {'artist': 'Bon Jovi', 'song': "Livin' on a Prayer",
         'reason': 'Stadium-sized optimism, whoa-oh included'},
    ],
    'energetic': [
        {'artist': 'Dua Lipa', 'song': 'Levitating',
         'reason': 'Disco-pop adrenaline with a relentless groove'},
        {'artist': 'The Weeknd', 'song': 'Blinding Lights',
         'reason': '80s synth-pop turbocharged for the dancefloor'},
        {'artist': 'Bad Bunny', 'song': 'Tití Me Preguntó',
         'reason': 'Dembow bounce that keeps energy at maximum'},
        {'artist': 'Beyoncé', 'song': 'BREAK MY SOUL',
         'reason': 'House revival built to make you move'},
        {'artist': 'Calvin Harris', 'song': 'Summer',
         'reason': 'EDM euphoria, a pure summer rush'},
        {'artist': 'Imagine Dragons', 'song': 'Believer',
         'reason': 'Anthemic rock with stadium-sized drums'},
        {'artist': 'Travis Scott', 'song': 'SICKO MODE',
         'reason': 'Trap production that hits like a wave'},
        {'artist': 'Rihanna', 'song': "Don't Stop The Music",
         'reason': 'Relentless club groove from start to finish'},
        {'artist': 'ABBA', 'song': 'Dancing Queen',
         'reason': 'Pure disco joy — impossible not to move'},
        {'artist': 'Kanye West', 'song': 'Stronger',
         'reason': 'Electronic hip-hop power surge'},
        {'artist': 'Doja Cat', 'song': 'Woman',
         'reason': 'Afrobeats-tinged swagger anthem'},
        {'artist': 'BTS', 'song': 'Dynamite',
         'reason': 'Funk-pop blast of pure happiness'},
        {'artist': 'Lady Gaga', 'song': 'Bad Romance',
         'reason': 'Electropop with a monstrous hook'},
        {'artist': 'Avicii', 'song': 'Wake Me Up',
         'reason': 'Folk-EDM festival ignition'},
        {'artist': 'Shakira', 'song': 'Waka Waka',
         'reason': 'World-Cup-sized party energy'},
    ],
    'relaxed': [
        {'artist': 'SZA', 'song': 'Snooze',
         'reason': 'Dreamy R&B that melts into the couch'},
        {'artist': 'Jack Johnson', 'song': 'Better Together',
         'reason': 'Sun-soaked acoustic calm'},
        {'artist': 'Norah Jones', 'song': "Don't Know Why",
         'reason': 'Late-night jazz calm'},
        {'artist': 'Khalid', 'song': 'Location',
         'reason': 'Warm alt-R&B slow burn'},
        {'artist': 'Tems', 'song': 'Free Mind',
         'reason': 'Airy Afrobeats-R&B drift'},
        {'artist': 'Bon Iver', 'song': 'Skinny Love',
         'reason': 'Minimal indie-folk tenderness'},
        {'artist': 'Daniel Caesar', 'song': 'Best Part',
         'reason': 'Silky guitar romance'},
        {'artist': 'Billie Eilish', 'song': 'ocean eyes',
         'reason': 'Weightless dream-pop float'},
        {'artist': 'Ed Sheeran', 'song': 'Thinking Out Loud',
         'reason': 'Gentle acoustic warmth'},
        {'artist': 'Frank Ocean', 'song': 'Ivy',
         'reason': 'Hazy guitar lull'},
        {'artist': 'Men I Trust', 'song': 'Show Me How',
         'reason': 'Dream-pop synth softness'},
        {'artist': 'Cigarettes After Sex', 'song': 'Apocalypse',
         'reason': 'Slowcore bedroom drift'},
        {'artist': 'Tyla', 'song': 'Water',
         'reason': 'Smooth amapiano-tinged calm'},
        {'artist': 'Tom Odell', 'song': 'Another Love',
         'reason': 'Piano-ballad haze'},
        {'artist': 'Vance Joy', 'song': 'Riptide',
         'reason': 'Breezy ukulele singalong'},
    ],
    'sad': [
        {'artist': 'Adele', 'song': 'Someone Like You',
         'reason': 'The breakup ballad that defined a decade'},
        {'artist': 'Billie Eilish', 'song': 'everything i wanted',
         'reason': 'Quiet despair under shimmering synths'},
        {'artist': 'Sam Smith', 'song': 'Stay With Me',
         'reason': 'Gospel-tinged plea of loneliness'},
        {'artist': 'Lewis Capaldi', 'song': 'Someone You Loved',
         'reason': 'Piano heartbreak anthem'},
        {'artist': 'Coldplay', 'song': 'Fix You',
         'reason': 'Slow-burn catharsis'},
        {'artist': 'Radiohead', 'song': 'Creep',
         'reason': 'Alienated 90s ache'},
        {'artist': 'Amy Winehouse', 'song': 'Back to Black',
         'reason': 'Soul-jazz farewell'},
        {'artist': 'Frank Ocean', 'song': 'White Ferrari',
         'reason': 'Meditative grief in falsetto'},
        {'artist': 'Adele', 'song': 'Hello',
         'reason': 'Long-distance regret'},
        {'artist': 'Lana Del Rey', 'song': 'Summertime Sadness',
         'reason': 'Cinematic melancholy'},
        {'artist': 'The Weeknd', 'song': 'Call Out My Name',
         'reason': 'Cold-hearted breakup R&B'},
        {'artist': 'SZA', 'song': 'Good Days',
         'reason': 'Hope tinged with sadness'},
        {'artist': 'Olivia Rodrigo', 'song': 'drivers license',
         'reason': 'Teen heartbreak epic'},
        {'artist': 'Bon Iver', 'song': 're: stacks',
         'reason': 'Sparse folk sorrow'},
        {'artist': 'James Blake', 'song': 'Retrograde',
         'reason': 'Electronic soul ache'},
    ],
    'romantic': [
        {'artist': 'Ed Sheeran', 'song': 'Perfect',
         'reason': 'The wedding-first-dance classic'},
        {'artist': 'John Legend', 'song': 'All of Me',
         'reason': 'Devoted piano love song'},
        {'artist': 'Alicia Keys', 'song': "If I Ain't Got You",
         'reason': 'Soulful declaration of love'},
        {'artist': 'Etta James', 'song': 'At Last',
         'reason': 'Timeless orchestral romance'},
        {'artist': 'Bruno Mars', 'song': 'Just the Way You Are',
         'reason': 'Sweet pop devotion'},
        {'artist': 'Daniel Caesar', 'song': 'Get You',
         'reason': 'Silky bedroom R&B'},
        {'artist': 'Taylor Swift', 'song': 'Lover',
         'reason': 'Dreamy folk-pop commitment'},
        {'artist': 'Beyoncé', 'song': 'Halo',
         'reason': 'Soaring love anthem'},
        {'artist': 'Sade', 'song': 'Smooth Operator',
         'reason': 'Silky late-night romance'},
        {'artist': 'Frank Ocean', 'song': 'Thinkin Bout You',
         'reason': 'Tender alt-R&B longing'},
        {'artist': "D'Angelo", 'song': 'Untitled (How Does It Feel)',
         'reason': 'Neo-soul intimacy'},
        {'artist': 'H.E.R.', 'song': 'Damage',
         'reason': 'Slow-burning R&B seduction'},
        {'artist': 'The Weeknd', 'song': 'Die For You',
         'reason': 'Cinematic devotion'},
        {'artist': 'Christina Perri', 'song': 'A Thousand Years',
         'reason': 'Eternal-love ballad'},
        {'artist': 'Elvis Presley', 'song': "Can't Help Falling in Love",
         'reason': 'Classic crooner romance'},
    ],
    'party': [
        {'artist': 'Rihanna', 'song': 'We Found Love',
         'reason': 'EDM-pop floor-filler'},
        {'artist': 'Pitbull', 'song': 'Give Me Everything',
         'reason': 'Club-pop at maximum velocity'},
        {'artist': 'LMFAO', 'song': 'Party Rock Anthem',
         'reason': 'Shuffle-inducing chaos'},
        {'artist': 'Beyoncé', 'song': 'Crazy in Love',
         'reason': 'Brass-driven dance explosion'},
        {'artist': 'Shakira', 'song': 'Hips Don\'t Lie',
         'reason': 'Global dance craze'},
        {'artist': 'Usher', 'song': 'Yeah!',
         'reason': 'Crunk&B club command'},
        {'artist': 'Mark Ronson', 'song': 'Uptown Funk',
         'reason': 'Funk-revival showstopper (ft. Bruno Mars)'},
        {'artist': 'Daft Punk', 'song': 'Get Lucky',
         'reason': 'Disco-electronic groove'},
        {'artist': 'Katy Perry', 'song': 'Last Friday Night (T.G.I.F.)',
         'reason': 'Party-chaos storytelling'},
        {'artist': 'Black Eyed Peas', 'song': 'I Gotta Feeling',
         'reason': 'Celebration anthem'},
        {'artist': 'Dua Lipa', 'song': "Don't Start Now",
         'reason': 'Disco-pop dance command'},
        {'artist': 'Bad Bunny', 'song': 'Dakiti',
         'reason': 'Reggaeton slow-burn party'},
        {'artist': 'Sean Paul', 'song': 'Temperature',
         'reason': 'Dancehall heat'},
        {'artist': 'Tiësto', 'song': 'The Business',
         'reason': 'Big-room EDM drop'},
        {'artist': 'David Guetta', 'song': 'Titanium',
         'reason': 'Hands-in-the-air EDM (ft. Sia)'},
    ],
    'focus': [
        {'artist': 'Ludovico Einaudi', 'song': 'Experience',
         'reason': 'Neoclassical piano flow'},
        {'artist': 'Nils Frahm', 'song': 'Says',
         'reason': 'Minimalist build for deep work'},
        {'artist': 'Bonobo', 'song': 'Kerala',
         'reason': 'Steady downtempo groove'},
        {'artist': 'Tycho', 'song': 'Awake',
         'reason': 'Warm instrumental focus'},
        {'artist': 'Explosions in the Sky', 'song': 'Your Hand in Mine',
         'reason': 'Wordless post-rock lift'},
        {'artist': 'Brian Eno', 'song': 'Music for Airports 1/1',
         'reason': 'Ambient pioneer calm'},
        {'artist': 'Khruangbin', 'song': 'Maria También',
         'reason': 'Hypnotic instrumental groove'},
        {'artist': 'Air', 'song': "La Femme d'Argent",
         'reason': 'Lounge-electronic drift'},
        {'artist': 'Ólafur Arnalds', 'song': 'Near Light',
         'reason': 'Soft piano focus'},
        {'artist': 'Four Tet', 'song': 'She Moves She',
         'reason': 'Glitchy calm repetition'},
        {'artist': 'Sigur Rós', 'song': 'Hoppípolla',
         'reason': 'Wordless emotional lift'},
        {'artist': 'Massive Attack', 'song': 'Teardrop',
         'reason': 'Trip-hop steady pulse'},
        {'artist': 'Miles Davis', 'song': 'So What',
         'reason': 'Cool jazz that never distracts'},
        {'artist': 'Nujabes', 'song': 'Feather',
         'reason': 'Jazzy hip-hop for concentration'},
        {'artist': 'Hans Zimmer', 'song': 'Time',
         'reason': 'Cinematic swell for big thinking'},
    ],
}


def mood_seeds(mood: str) -> List[Tuple[str, str]]:
    """Return 6 (artist, song) seed pairs for a canonical mood."""
    try:
        pool = MOOD_SONG_POOLS.get((mood or '').lower())
        if not pool:
            return []
        return [(s['artist'], s['song']) for s in pool[:6]]
    except Exception:
        return []


def _similar_quick(artist: str, song: str, mood: str,
                   cache: Dict[str, List[Dict]]) -> List[Dict]:
    """Best-effort live enhancement via get_similar_songs.

    Hard timeout + in-memory cache: a slow or failing API is treated as
    "down" and [] is returned so the caller can use its local answer.
    Never raises.
    """
    try:
        key = f"{artist} - {song} - {mood}".lower()
        if key in cache:
            return list(cache[key])
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(get_similar_songs, artist, song, mood)
                res = fut.result(timeout=_SIMILAR_TIMEOUT)
        except Exception:
            return []
        out = []
        if isinstance(res, list):
            for s in res:
                if not isinstance(s, dict):
                    continue
                a = str(s.get('artist') or '').strip()
                t = str(s.get('name') or s.get('song') or '').strip()
                if a and t:
                    out.append({'artist': a, 'name': t,
                                'reason': str(s.get('reason') or '')})
        cache[key] = out
        return list(out)
    except Exception:
        return []


def _mood_lastfm_tag_tracks(mood: str, limit: int = 12) -> List[Dict]:
    """Listener-favorites mood source: Last.fm tag.getTopTracks (REST, ~0.5s).

    12-hour in-memory cache per mood. Returns [{'artist','name'}]
    deduplicated, or [] when the API is down/slow. Never raises.
    """
    import os as _os
    import time as _time
    try:
        import requests as _requests
    except Exception:
        return []
    mood = (mood or '').lower()
    tag = _MOOD_LASTFM_TAG.get(mood, mood)
    try:
        entry = _MOOD_TAG_CACHE.get(tag)
        if entry and (_time.time() - entry[0]) < _MOOD_TAG_TTL_SECS:
            return list(entry[1])
        api_key = _os.environ.get('LASTFM_API_KEY', '')
        if not api_key:
            return []
        r = _requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={"method": "tag.gettoptracks", "tag": tag,
                    "api_key": api_key, "format": "json", "limit": limit},
            timeout=8,
            headers={"User-Agent": "LyricsMasterBot/1.0"})
        tracks = ((r.json() or {}).get("tracks") or {}).get("track") or []
        out, seen = [], set()
        for t in tracks:
            if not isinstance(t, dict):
                continue
            a = str((t.get('artist') or {}).get('name') or '').strip()
            name = str(t.get('name') or '').strip()
            if not a or not name:
                continue
            # Skip classical mega-titles and junk that look bad in a mix.
            if len(name) > 60:
                continue
            k = (a.lower(), name.lower())
            if k in seen:
                continue
            seen.add(k)
            out.append({'artist': a, 'name': name})
        _MOOD_TAG_CACHE[tag] = (_time.time(), out)
        # Cap cache size (7 moods max, but be tidy).
        while len(_MOOD_TAG_CACHE) > 12:
            _MOOD_TAG_CACHE.pop(next(iter(_MOOD_TAG_CACHE)))
        return list(out)
    except Exception:
        return []


def get_mood_mix(mood: str, n: int = 5) -> List[Dict]:
    """Mood mix — LIVE-first across three tiers, all current.

    1. Fresh main-chart releases (<=24 months): title keyword match, then
       Apple genre-tag match.
    2. Shortfall tier: iTunes genre feeds (calm moods) + iTunes term
       search (all moods) — still fresh-only, junk/AI-farm guarded.
    3. Listener favorites: the live Last.fm tag chart (12h cached).
    The local MOOD_SONG_POOLS only fills a shortfall or serves when every
    live source is down — so the user always gets a mix.

    Returns [{'artist','name','source'}] with source in
    {'fresh','tag','pool'}.  Never raises.
    """
    try:
        mood = (mood or '').lower()
        internal = _MOOD_INTERNAL.get(mood, 'happy')
        n = max(1, min(int(n or 5), 10))
        seen_keys: set = set()
        seen_artists: set = set()
        seen_titles: set = set()
        out = _tier12_picks(get_fresh_entries(), mood, internal, n,
                            seen_keys, seen_artists, seen_titles)
        if len(out) < n:
            out += _tier3_picks(mood, internal, n - len(out),
                               seen_keys, seen_artists, seen_titles)
        if len(out) < n:
            for s in _mood_lastfm_tag_tracks(mood, limit=max(n * 2, 10)):
                if len(out) >= n:
                    break
                if _claim_pick(out, seen_keys, seen_artists,
                               s.get('artist'), s.get('name'), 'tag', 'tag',
                               seen_titles):
                    pass
        if len(out) < n:
            pool = MOOD_SONG_POOLS.get(mood) or []
            for s in _rng.sample(pool, min(len(pool), n * 2)):
                if len(out) >= n:
                    break
                akey = (str(s.get('artist', '')).lower(),
                        str(s.get('song', '')).lower())
                if akey in seen_keys:
                    continue
                seen_keys.add(akey)
                out.append({'artist': s['artist'], 'name': s['song'],
                            'source': 'pool',
                            'reason': s.get('reason', '')})
        return out[:n]
    except Exception as e:
        logger.debug(f"get_mood_mix failed: {e}")
        return []

# ──────────────────────────────────────────────────────────────────────────────
# Playlist extension
# ──────────────────────────────────────────────────────────────────────────────
_DASH_RE = re.compile(r'\s*[-\u2013\u2014]\s*')  # hyphen, en dash, em dash


def parse_extend_lines(text: str) -> List[Dict]:
    """Parse "Artist - Title" lines (also en/em dashes) into [{'artist','song'}].

    Strips quotes/whitespace; skips garbage lines (no separator, empty side,
    or lines that are too short to be a real entry).  Never raises.
    """
    try:
        out = []
        for raw in (text or '').splitlines():
            line = raw.strip().strip('"\'“”‘’').strip()
            if not line or len(line) < 5:
                continue
            parts = _DASH_RE.split(line, maxsplit=1)
            if len(parts) != 2:
                continue
            artist, song = parts[0].strip().strip('"\'“”‘’'), parts[1].strip().strip('"\'“”‘’')
            if len(artist) < 2 or len(song) < 2:
                continue
            # Skip lines that are clearly not "Artist - Title" (e.g. bullet prose)
            if len(song.split()) > 12:
                continue
            out.append({'artist': artist, 'song': song})
        return out
    except Exception:
        return []


def get_recent_picks(user_id: int, n: int = 3) -> List[Dict]:
    """Last n picks from artist_service._recent_random_picks as [{'artist','song'}].

    Most-recent-first.  Note: artist_service stores these lowercased, so the
    returned names are lowercase — that is inherited, not a bug here.
    [] when the user has no history.  Never raises.
    """
    try:
        dq = _recent_random_picks.get(user_id)
        if not dq:
            return []
        items = list(dq)[-max(1, int(n or 3)):]
        out = []
        for item in reversed(items):
            artist, sep, song = str(item).partition(' - ')
            if not sep:
                continue
            artist, song = artist.strip(), song.strip()
            if artist and song:
                out.append({'artist': artist, 'song': song})
        return out
    except Exception:
        return []


_GENRE_DISPLAY = {'rnb': 'R&B', 'hiphop': 'Hip-Hop'}


def blend_vibe(songs: List[Dict]) -> Dict:
    """Blend a song list into {'genre','mood','label'}.

    genre  = most common via ARTIST_GENRE_MAP (default 'pop').
    mood   = most common title-keyword mood guess (canonical MOOD_BUTTONS key).
    label  = e.g. "Afrobeats • Energetic".
    Never raises; {} only if `songs` is empty/invalid.
    """
    try:
        songs = [s for s in (songs or []) if isinstance(s, dict)]
        if not songs:
            return {}
        genre_votes: Dict[str, int] = {}
        mood_votes: Dict[str, int] = {}
        for s in songs:
            artist = str(s.get('artist') or '')
            title = str(s.get('song') or s.get('name') or '')
            g = ARTIST_GENRE_MAP.get(artist.lower().strip(), 'pop')
            genre_votes[g] = genre_votes.get(g, 0) + 1
            tl = title.lower()
            for kw, mood in _MOOD_KEYWORDS_SORTED:
                if kw in tl:
                    mood_votes[mood] = mood_votes.get(mood, 0) + 1
                    break  # one vote per song
        genre = max(genre_votes, key=lambda k: genre_votes[k])
        if mood_votes:
            # Tie-break in MOOD_BUTTONS order for determinism.
            order = [m for _, m in MOOD_BUTTONS]
            mood = max(mood_votes,
                       key=lambda k: (mood_votes[k], -order.index(k)))
        else:
            mood = 'relaxed'
        g_display = _GENRE_DISPLAY.get(genre, genre.title())
        label = f"{g_display} • {mood.title()}"
        return {'genre': genre, 'mood': mood, 'label': label}
    except Exception:
        return {}


def get_extend_recs(songs: List[Dict], n: int = 5) -> List[Dict]:
    """Vibe-blended recommendations — PRIMARY is fully local (works offline).

    Filters GENRE_TOP_SONGS[blended genre] + genre-matched RANDOM_SONGS_POOL
    entries, excluding the input songs, each with a reason referencing the
    vibe.  Enhancement: optionally tops up with get_similar_songs results
    (hard timeout; ignored when the API is down).  Returns
    [{'artist','name','reason'}]; [] on failure.  Never raises.
    """
    try:
        songs = [s for s in (songs or []) if isinstance(s, dict)]
        if not songs:
            return []
        n = max(1, int(n or 5))
        vibe = blend_vibe(songs) or {'genre': 'pop', 'mood': 'relaxed',
                                     'label': 'Pop • Relaxed'}
        genre, mood, label = vibe['genre'], vibe['mood'], vibe['label']

        excluded = set()
        for s in songs:
            title = str(s.get('song') or s.get('name') or '')
            excluded.add((str(s.get('artist') or '').lower().strip(),
                          title.lower().strip()))

        def _key(a: str, t: str) -> Tuple[str, str]:
            return (a.lower().strip(), t.lower().strip())

        cands: List[Dict] = []
        for e in GENRE_TOP_SONGS.get(genre, []):
            if _key(e['artist'], e['song']) in excluded:
                continue
            note = e.get('note') or f'a top {genre} pick'
            cands.append({'artist': e['artist'], 'name': e['song'],
                          'reason': f"Fits your {label} vibe — {note}"})
        for e in RANDOM_SONGS_POOL:
            if ARTIST_GENRE_MAP.get(e['artist'].lower(), 'pop') != genre:
                continue
            if _key(e['artist'], e['song']) in excluded:
                continue
            if any(_key(c['artist'], c['name']) == _key(e['artist'], e['song'])
                   for c in cands):
                continue
            cands.append({'artist': e['artist'], 'name': e['song'],
                          'reason': f"Matches your {label} vibe"})
        _rng.shuffle(cands)
        out = cands[:n]

        # Optional live enhancement: top up with similar songs of the first
        # input song (blended mood), deduped, still capped at n.
        first = songs[0]
        fa = str(first.get('artist') or '').strip()
        ft = str(first.get('song') or first.get('name') or '').strip()
        if fa and ft:
            live = _similar_quick(fa, ft, mood, _EXTEND_LIVE_CACHE)
            seen = {_key(c['artist'], c['name']) for c in out} | excluded
            for s in live:
                if len(out) >= n:
                    break
                k = _key(s['artist'], s['name'])
                if k in seen:
                    continue
                seen.add(k)
                out.append({'artist': s['artist'], 'name': s['name'],
                            'reason': s.get('reason') or
                            f"Fits your {label} vibe"})
        return out
    except Exception as e:
        logger.debug(f"get_extend_recs failed: {e}")
        return []

# ──────────────────────────────────────────────────────────────────────────────
# Theme interpretation & matching
# ──────────────────────────────────────────────────────────────────────────────
_STOPWORDS = frozenset({
    'i', 'me', 'my', 'mine', 'you', 'your', 'yours', 'we', 'our', 'they',
    'he', 'she', 'it', 'its', 'a', 'an', 'the', 'and', 'or', 'but', 'of',
    'to', 'in', 'on', 'at', 'for', 'with', 'about', 'that', 'this', 'these',
    'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am',
    'do', 'does', 'did', 'done', 'have', 'has', 'had', 'having', 'will',
    'would', 'can', 'could', 'should', 'shall', 'may', 'might', 'must',
    'not', 'no', 'yes', 'so', 'as', 'if', 'then', 'than', 'too', 'very',
    'just', 'like', 'what', 'when', 'where', 'which', 'who', 'whom',
    'how', 'why', 'there', 'here', 'from', 'into', 'over', 'under',
    'again', 'once', 'all', 'any', 'some', 'more', 'most', 'other',
    'such', 'only', 'own', 'same', 'up', 'down', 'out', 'off', 'want',
    'wants', 'need', 'needs', 'feel', 'feeling', 'feels', 'find', 'give',
    'make', 'songs', 'song', 'music', 'track', 'tracks', 'tune', 'tunes',
    'sound', 'sounds', 'vibe', 'vibes', 'playlist', 'mix', 'list',
})

# Genre hint words -> GENRE_TOP_SONGS key.  Checked longest-first.
_GENRE_HINTS: List[Tuple[str, str]] = sorted([
    ('afrobeats', 'afrobeats'), ('afrobeat', 'afrobeats'), ('amapiano', 'afrobeats'),
    ('afro', 'afrobeats'), ('afropop', 'afrobeats'),
    ('hip-hop', 'rap'), ('hip hop', 'rap'), ('hiphop', 'rap'),
    ('rap', 'rap'), ('trap', 'rap'),
    ('r&b', 'rnb'), ('rnb', 'rnb'), ('r and b', 'rnb'), ('soul', 'soul'),
    ('neo-soul', 'soul'), ('neosoul', 'soul'),
    ('k-pop', 'kpop'), ('kpop', 'kpop'), ('korean', 'kpop'),
    ('reggaeton', 'latin'), ('latin', 'latin'), ('spanish', 'latin'),
    ('salsa', 'latin'), ('bachata', 'latin'),
    ('country', 'country'), ('folk', 'country'),
    ('rock', 'rock'), ('punk', 'rock'), ('metal', 'rock'), ('indie', 'rock'),
    ('alternative', 'rock'), ('grunge', 'rock'),
    ('pop', 'pop'), ('electronic', 'pop'), ('edm', 'pop'), ('dance', 'pop'),
    ('house', 'pop'), ('techno', 'pop'), ('disco', 'pop'),
    ('jazz', 'soul'), ('blues', 'soul'), ('gospel', 'soul'),
], key=lambda kv: len(kv[0]), reverse=True)

_THEME_SYSTEM = (
    'You are a music theme parser. The user describes a theme like '
    '"songs about starting over". Reply with JSON only (the word JSON is '
    'required here): an object with keys "mood" (one of: energetic, relaxed, '
    'sad, romantic, party, focus), "keywords" (array of 2-6 meaningful '
    'lowercase words from the theme, no stopwords), and "genres" (array of '
    'zero or more of: afrobeats, pop, rap, rnb, rock, latin, country, soul, '
    'kpop). Example: {"mood": "relaxed", "keywords": ["fresh", "start", '
    '"new", "beginnings"], "genres": []}'
)

_KNOWN_GENRES = set(GENRE_TOP_SONGS.keys())


def _validate_theme(data) -> Optional[Dict]:
    """Validate/normalize an OpenAI theme response; None if unusable."""
    try:
        if not isinstance(data, dict):
            return None
        mood = normalize_mood(str(data.get('mood') or '')) or 'relaxed'
        kws = [str(k).lower().strip() for k in (data.get('keywords') or [])
               if str(k).strip()]
        kws = [k for k in kws if k not in _STOPWORDS][:6]
        genres = [str(g).lower().strip() for g in (data.get('genres') or [])
                  if str(g).lower().strip() in _KNOWN_GENRES]
        return {'mood': mood, 'keywords': kws, 'genres': genres}
    except Exception:
        return None


def _theme_keyword_fallback(text: str) -> Dict:
    """High-quality local theme parsing — the PRIMARY path (no API needed)."""
    tl = text.lower()
    words = re.findall(r"[a-z0-9']+", tl)
    keywords: List[str] = []
    for w in words:
        w = w.strip("'")
        if len(w) > 2 and w not in _STOPWORDS and w not in keywords:
            keywords.append(w)
        if len(keywords) >= 6:
            break

    # Mood: vote by keyword hits, tie-break in MOOD_BUTTONS order.
    votes: Dict[str, int] = {}
    for kw, mood in _MOOD_KEYWORDS_SORTED:
        if kw in tl:
            votes[mood] = votes.get(mood, 0) + 1
    if votes:
        order = [m for _, m in MOOD_BUTTONS]
        mood = max(votes, key=lambda k: (votes[k], -order.index(k)))
    else:
        mood = 'relaxed'

    # Genres: hint-word scan.
    genres: List[str] = []
    for hint, g in _GENRE_HINTS:
        if hint in tl and g not in genres:
            genres.append(g)

    return {'mood': mood, 'keywords': keywords, 'genres': genres}


def interpret_theme(text: str) -> Dict:
    """Interpret a theme description -> {'mood','keywords','genres'}.

    PRIMARY is the high-quality local keyword fallback (no API, no quota).
    Enhancement: OpenAI is tried first when a client is available, with a
    10s timeout and an in-memory cache so repeat themes never re-call the
    API.  Never raises.
    """
    safe = {'mood': 'relaxed', 'keywords': [], 'genres': []}
    try:
        raw = (text or '').strip()
        if not raw:
            return dict(safe)
        key = ' '.join(raw.lower().split())
        if key in _THEME_CACHE:
            return dict(_THEME_CACHE[key])

        # Optional OpenAI enhancement.
        try:
            from services.nlp_router import _MODEL, _get_client
            client = _get_client()
            if client is not None:
                resp = client.responses.create(
                    model=_MODEL,
                    input=[{"role": "system", "content": _THEME_SYSTEM},
                           {"role": "user", "content": raw}],
                    text={"format": {"type": "json_object"}},
                    timeout=10,
                )
                parsed = _validate_theme(json.loads(resp.output_text))
                if parsed:
                    _THEME_CACHE[key] = parsed
                    return dict(parsed)
        except Exception as e:
            logger.debug(f"interpret_theme OpenAI enhancement failed: {e}")

        parsed = _theme_keyword_fallback(raw)
        _THEME_CACHE[key] = parsed
        return dict(parsed)
    except Exception:
        return dict(safe)


def match_theme(theme: Dict, n: int = 5) -> List[Dict]:
    """Score local candidate songs against a theme — 100% local, no API calls.

    Candidates: RANDOM_SONGS_POOL + all GENRE_TOP_SONGS + get_quiz_songs().
    Scoring: keyword overlap in the title (+artist), genre bonus, mood bonus.
    Returns top n as [{'artist','song','reason'}] with the reason referencing
    the theme.  Never raises.
    """
    try:
        theme = theme or {}
        keywords = [str(k).lower() for k in (theme.get('keywords') or [])
                    if str(k).strip()]
        mood = str(theme.get('mood') or '').lower()
        genres = {str(g).lower() for g in (theme.get('genres') or [])}

        # Build + dedupe candidate pool.
        cands: List[Dict] = []
        seen = set()

        def _add(artist: str, song: str):
            k = (str(artist).lower().strip(), str(song).lower().strip())
            if k[0] and k[1] and k not in seen:
                seen.add(k)
                cands.append({'artist': str(artist).strip(),
                              'song': str(song).strip()})

        for e in RANDOM_SONGS_POOL:
            _add(e.get('artist', ''), e.get('song', ''))
        for lst in GENRE_TOP_SONGS.values():
            for e in lst:
                _add(e.get('artist', ''), e.get('song', ''))
        try:
            for e in get_quiz_songs():
                _add(e.get('artist', ''), e.get('song', ''))
        except Exception:
            pass
        if not cands:
            return []

        def _title_mood(title: str) -> Optional[str]:
            tl = title.lower()
            for kw, m in _MOOD_KEYWORDS_SORTED:
                if kw in tl:
                    return m
            return None

        scored = []
        for c in cands:
            score = 0
            title_l = c['song'].lower()
            words = set(re.findall(r"[a-z0-9']+", title_l))
            for kw in keywords:
                if kw in words:
                    score += 3          # whole-word title hit
                elif kw in title_l:
                    score += 2          # substring title hit
                elif kw in c['artist'].lower():
                    score += 1          # artist hit
            if genres and ARTIST_GENRE_MAP.get(c['artist'].lower(), 'pop') in genres:
                score += 2
            if mood and _title_mood(c['song']) == mood:
                score += 1
            scored.append((score, c))

        scored.sort(key=lambda s: (-s[0], s[1]['artist'].lower(),
                                   s[1]['song'].lower()))
        n = max(1, int(n or 5))

        if keywords:
            short = ' '.join(keywords[:3])
            reason = f"Matches '{short}': {' & '.join(keywords[:4])}"
        elif mood:
            reason = f"Fits the {mood} mood"
        else:
            reason = "Picked for your theme"

        return [{'artist': c['artist'], 'song': c['song'], 'reason': reason}
                for _, c in scored[:n]]
    except Exception as e:
        logger.debug(f"match_theme failed: {e}")
        return []

# ──────────────────────────────────────────────────────────────────────────────
# Throwback decades — fully local curated pools
# ──────────────────────────────────────────────────────────────────────────────
DECADE_POOLS: Dict[str, List[Dict]] = {
    '80s': [
        {'artist': 'Michael Jackson', 'song': 'Billie Jean',
         'fact': 'The Motown 25 moonwalk performance turned it into a global phenomenon.'},
        {'artist': 'Madonna', 'song': 'Like a Prayer',
         'fact': 'Its video sparked a Vatican condemnation — and massive sales.'},
        {'artist': 'Prince', 'song': 'Purple Rain',
         'fact': 'Recorded partly live at First Avenue in Minneapolis.'},
        {'artist': 'Whitney Houston', 'song': 'I Wanna Dance with Somebody',
         'fact': 'Her second US #1, from the best-selling album of 1987.'},
        {'artist': 'Bon Jovi', 'song': "Livin' on a Prayer",
         'fact': 'The talk-box intro was almost left out of the final mix.'},
        {'artist': "Guns N' Roses", 'song': "Sweet Child O' Mine",
         'fact': "Slash's opening riff started as a warm-up exercise."},
        {'artist': 'a-ha', 'song': 'Take On Me',
         'fact': 'Its animated video took 16 weeks to produce.'},
        {'artist': 'Queen', 'song': 'Under Pressure',
         'fact': 'The bassline was later famously sampled for "Ice Ice Baby".'},
        {'artist': 'U2', 'song': 'With or Without You',
         'fact': 'Their first US #1 single.'},
        {'artist': 'The Police', 'song': 'Every Breath You Take',
         'fact': 'Won the 1984 Grammy for Song of the Year.'},
        {'artist': 'Cyndi Lauper', 'song': 'Girls Just Want to Have Fun'},
        {'artist': 'Journey', 'song': "Don't Stop Believin'"},
        {'artist': 'Tears for Fears', 'song': 'Everybody Wants to Rule the World'},
        {'artist': 'New Order', 'song': 'Blue Monday',
         'fact': 'The best-selling 12-inch single of all time.'},
        {'artist': 'Rick Astley', 'song': 'Never Gonna Give You Up',
         'fact': 'Became the "Rickroll" meme decades after release.'},
        {'artist': 'Run-DMC', 'song': 'Walk This Way',
         'fact': 'The Aerosmith collab that broke rap into mainstream rock.'},
    ],
    '90s': [
        {'artist': 'Nirvana', 'song': 'Smells Like Teen Spirit',
         'fact': 'Named after a deodorant brand scrawled on Kurt Cobain\'s wall.'},
        {'artist': 'Whitney Houston', 'song': 'I Will Always Love You',
         'fact': 'Spent 14 weeks at US #1 — a record at the time.'},
        {'artist': 'Backstreet Boys', 'song': 'I Want It That Way'},
        {'artist': 'Britney Spears', 'song': '...Baby One More Time',
         'fact': 'Her debut single, released when she was 16.'},
        {'artist': 'Oasis', 'song': 'Wonderwall',
         'fact': 'One of the most-streamed 90s songs in the world.'},
        {'artist': 'Radiohead', 'song': 'Creep'},
        {'artist': 'TLC', 'song': 'Waterfalls',
         'fact': 'The first #1 on the Billboard Hot 100 with an AIDS-awareness message.'},
        {'artist': 'Spice Girls', 'song': 'Wannabe',
         'fact': 'Recorded in under 30 minutes.'},
        {'artist': 'Eminem', 'song': 'My Name Is',
         'fact': 'His first major hit, produced by Dr. Dre.'},
        {'artist': 'Lauryn Hill', 'song': 'Doo Wop (That Thing)'},
        {'artist': 'Mariah Carey', 'song': 'Fantasy',
         'fact': 'Pioneered the pop/hip-hop sample collab with O.D.B.'},
        {'artist': 'Green Day', 'song': 'Basket Case'},
        {'artist': 'The Notorious B.I.G.', 'song': 'Juicy',
         'fact': 'Built on Mtume\'s "Juicy Fruit" — a rags-to-riches classic.'},
        {'artist': 'Alanis Morissette', 'song': 'Ironic'},
        {'artist': 'Celine Dion', 'song': 'My Heart Will Go On',
         'fact': "Written for Titanic; Dion didn't want to record it at first."},
        {'artist': 'Dr. Dre', 'song': "Nuthin' but a 'G' Thang",
         'fact': 'Introduced Snoop Dogg to the world.'},
    ],
    '2000s': [
        {'artist': 'Outkast', 'song': 'Hey Ya!',
         'fact': 'Won the Grammy for Record of the Year in 2004.'},
        {'artist': 'Beyoncé', 'song': 'Crazy in Love',
         'fact': 'Her debut solo single — 8 weeks at US #1.'},
        {'artist': 'Eminem', 'song': 'Lose Yourself',
         'fact': 'First hip-hop song to win the Oscar for Best Original Song.'},
        {'artist': 'Coldplay', 'song': 'Yellow'},
        {'artist': 'Usher', 'song': 'Yeah!',
         'fact': 'Spent 12 weeks at #1, defining mid-2000s R&B.'},
        {'artist': 'Rihanna', 'song': 'Umbrella',
         'fact': 'Her breakout — 10 weeks at #1 in the UK.'},
        {'artist': 'Amy Winehouse', 'song': 'Rehab'},
        {'artist': 'The White Stripes', 'song': 'Seven Nation Army',
         'fact': 'Its riff became a global stadium chant.'},
        {'artist': 'Kanye West', 'song': 'Gold Digger',
         'fact': '10 weeks at US #1 in 2005.'},
        {'artist': 'Justin Timberlake', 'song': 'Cry Me a River'},
        {'artist': 'Alicia Keys', 'song': "Fallin'",
         'fact': 'Won Song of the Year at the 2002 Grammys.'},
        {'artist': 'Linkin Park', 'song': 'In the End'},
        {'artist': 'Shakira', 'song': 'Hips Don\'t Lie',
         'fact': 'One of the best-selling singles of the 2000s.'},
        {'artist': 'Gnarls Barkley', 'song': 'Crazy',
         'fact': 'First song to top the UK chart on downloads alone.'},
        {'artist': 'Lady Gaga', 'song': 'Poker Face',
         'fact': 'Topped charts in 20 countries.'},
        {'artist': 'Kings of Leon', 'song': 'Sex on Fire'},
    ],
    '2010s': [
        {'artist': 'Adele', 'song': 'Rolling in the Deep',
         'fact': 'Won Grammy Record and Song of the Year in 2012.'},
        {'artist': 'Ed Sheeran', 'song': 'Shape of You',
         'fact': 'One of the most-streamed songs in Spotify history.'},
        {'artist': 'Drake', 'song': "God's Plan",
         'fact': 'Its video gave away nearly $1M to people in Miami.'},
        {'artist': 'Billie Eilish', 'song': 'bad guy'},
        {'artist': 'Lorde', 'song': 'Royals',
         'fact': 'Written when Lorde was just 15.'},
        {'artist': 'Pharrell Williams', 'song': 'Happy',
         'fact': 'Spent 10 weeks at US #1 in 2014.'},
        {'artist': 'Mark Ronson', 'song': 'Uptown Funk',
         'fact': '14 weeks at US #1 (ft. Bruno Mars).'},
        {'artist': 'Sia', 'song': 'Chandelier'},
        {'artist': 'The Weeknd', 'song': 'Blinding Lights',
         'fact': "Billboard's all-time #1 Hot 100 song."},
        {'artist': 'Luis Fonsi', 'song': 'Despacito',
         'fact': 'First mostly-Spanish song to hit 1B YouTube views (ft. Daddy Yankee).'},
        {'artist': 'Taylor Swift', 'song': 'Shake It Off'},
        {'artist': 'Bruno Mars', 'song': '24K Magic',
         'fact': 'Won Record of the Year at the 2018 Grammys.'},
        {'artist': 'Kendrick Lamar', 'song': 'HUMBLE.'},
        {'artist': 'Dua Lipa', 'song': 'New Rules'},
        {'artist': 'Post Malone', 'song': 'rockstar',
         'fact': 'His first US #1 (ft. 21 Savage).'},
        {'artist': 'Ariana Grande', 'song': 'thank u, next'},
    ],
}

_DECADE_ALIASES = {
    '80s': ['80s', '80', 'eighties', '1980s', '1980', "'80s", '80 s'],
    '90s': ['90s', '90', 'nineties', '1990s', '1990', "'90s", '90 s'],
    '2000s': ['2000s', '2000', 'noughties', 'aughts', '00s', '00', '2000 s'],
    '2010s': ['2010s', '2010', 'twenty-tens', 'tens', '10s', 'twenty tens'],
}


def normalize_decade(text: str) -> str:
    """Map free text to '80s'/'90s'/'2000s'/'2010s'; anything else -> random."""
    try:
        t = ' '.join((text or '').lower().split())
        for decade, aliases in _DECADE_ALIASES.items():
            if t in aliases:
                return decade
        # Bare 4-digit years ("1995", "2003") -> their decade.
        m = re.search(r'\b(19[89]\d|20[01]\d)\b', t)
        if m:
            year = int(m.group(1))
            if 1980 <= year <= 1989:
                return '80s'
            if 1990 <= year <= 1999:
                return '90s'
            if 2000 <= year <= 2009:
                return '2000s'
            if 2010 <= year <= 2019:
                return '2010s'
        return _rng.choice(list(DECADE_POOLS.keys()))
    except Exception:
        return _rng.choice(list(DECADE_POOLS.keys()))


def get_throwback(decade: str, n: int = 5) -> List[Dict]:
    """Random n picks [{'artist','song','fact'}] — fully local, never raises."""
    try:
        decade = normalize_decade(decade)
        pool = DECADE_POOLS.get(decade, [])
        if not pool:
            return []
        n = max(1, min(int(n or 5), len(pool)))
        return [{'artist': s['artist'], 'song': s['song'],
                 'fact': s.get('fact')} for s in _rng.sample(pool, n)]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# New music — Apple chart (1-hour cached) with honest curated fallback
# ──────────────────────────────────────────────────────────────────────────────
def get_new_music(genre: Optional[str] = None,
                  n: int = 5) -> Tuple[List[Dict], bool]:
    """([{'artist','song','note'}], is_live).

    Uses artist_service.get_trending_songs() (live Apple chart, 1-hour cache)
    and _get_live_genre_songs() when the genre maps via GENRE_ALIASES /
    APPLE_GENRE_MAP.  When the chart fetch fails or is empty, falls back to
    the curated TRENDING_SONGS / GENRE_TOP_SONGS pools and returns
    is_live=False — the 'note' always labels the source honestly.
    Never raises.
    """
    try:
        n = max(1, int(n or 5))
    except Exception:
        n = 5
    try:
        if genre:
            g = str(genre).lower().strip()
            resolved = GENRE_ALIASES.get(g, g)
            if resolved in APPLE_GENRE_MAP:
                try:
                    live = _get_live_genre_songs(resolved)
                except Exception:
                    live = None
                if live:
                    return ([dict(s) for s in live[:n]], True)
            pool = GENRE_TOP_SONGS.get(resolved)
            if pool:
                picks = _rng.sample(pool, min(n, len(pool)))
                return ([dict(s) for s in picks], False)
            return ([], False)

        try:
            songs, is_live = get_trending_songs()
        except Exception:
            songs, is_live = [], False
        songs = songs or []
        if songs:
            out = []
            for s in songs[:n]:
                d = dict(s)
                d.setdefault('note',
                             'Charting now on Apple Music' if is_live
                             else 'Popular right now')
                out.append(d)
            return (out, bool(is_live))

        # Chart empty/down: curated fallback, honestly labeled.
        picks = _rng.sample(TRENDING_SONGS, min(n, len(TRENDING_SONGS)))
        return ([dict(s) for s in picks], False)
    except Exception as e:
        logger.debug(f"get_new_music failed: {e}")
        return ([], False)
