import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

YOUTUBE_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

# "play something by X" / "give me songs by X" → artist-based recommend.
# Must be compiled once and checked BEFORE the generic YouTube keyword scan
# because 'play' sits in YOUTUBE_KEYWORDS and would wrongly capture these.
_PLAY_BY_ARTIST_RE = re.compile(
    r'^(?:play(?:\s+me)?|give\s+me|get\s+me|show\s+me|find\s+me|put\s+on)\s+'
    r'(?:something|anything|songs?|music|a\s+song|some\s+music|tracks?)\s+'
    r'(?:by|from)\s+(.+)$',
    re.IGNORECASE,
)

# "Artist - Song" explicit structured format.
# Matches inputs like "Gemini - Hola", "Radiohead - Creep", etc.
# Used as a last resort in detect_intent, after all keyword checks.
_ARTIST_SONG_RE = re.compile(
    r'^(.{2,60}?)\s*[-–—]\s*(.{2,60})$',
    re.IGNORECASE,
)

# "Song by Artist" free-form pattern, e.g. "water by tyla".
# Lets users skip the "Artist - Song" format for the most natural phrasing.
_BY_SONG_RE = re.compile(
    r'^(.{2,60}?)\s+by\s+(.{2,60})$',
    re.IGNORECASE,
)

# "play <song>" / "put on <song>" — the user wants the song itself.
# Checked right after "play something by X" (→ recommend) and before the
# generic YouTube keyword scan: the song dashboard already embeds the video
# link, so the richer 'song' intent wins unless the text explicitly says
# youtube/video/mp3/audio (those keep the old youtube/mp3 intents).
_PLAY_SONG_RE = re.compile(
    r'^(?:can you\s+|could you\s+)?(?:please\s+)?(?:play|put on)\s+(.+?)[.!?]*$',
    re.IGNORECASE,
)

# "who sings/sang <song>" — the answer is the artist, shown front and center
# on the song dashboard, so route there.
_WHO_SINGS_RE = re.compile(r'^who\s+sings\s+(.+?)\??$', re.IGNORECASE)
_WHO_SANG_RE  = re.compile(r'^who\s+sang\s+(.+?)\??$',  re.IGNORECASE)

# "find/show/get/give me <X>" — X is an artist when we know them, else a song.
_FIND_ME_RE = re.compile(
    r'^(?:find|show|get|give)\s+me\s+(.+?)[.!?]*$',
    re.IGNORECASE,
)

# "that song that goes <lyrics fragment>" — search by the fragment.
_THAT_SONG_RE = re.compile(
    r'^(?:that|the) song that goes\s+(.+?)[.!?]*$',
    re.IGNORECASE,
)

# First words that mark the input as a question — those stay with the NLP layer.
_QUESTION_WORDS = frozenset({
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
    'is', 'are', 'was', 'were', 'do', 'does', 'did', 'can', 'could',
})

# Pronouns can never be an artist name — guards titles like "Stand By Me"
# from being misread as "<pronoun> - <rest>".
_PRONOUNS = frozenset({'me', 'you', 'him', 'her', 'them', 'us', 'it'})

# Generic placeholders on the song side: "songs by adele" → recommend adele.
_GENERIC_SONG_WORDS = frozenset({
    'song', 'songs', 'music', 'track', 'tracks',
    'something', 'anything', 'tune', 'tunes',
})

LYRICS_KEYWORDS = [
    'lyrics', 'lyric', 'words to', 'words of', 'text of', 'text for',
    'show me the lyrics', 'get lyrics', 'find lyrics', 'what are the lyrics',
    'sing', 'how does .* go',
]

RECOMMEND_KEYWORDS = [
    'similar to', 'songs like', 'music like', 'recommend', 'suggestion',
    'suggest', 'what should i listen', 'something like', 'more like',
    'like this', 'what else', 'similar songs', 'similar music',
]

# "recommend something new" → fresh releases, not a song literally called
# "something new".  Checked against the cleaned remainder (see below).
_FRESH_WORDS = frozenset({'new', 'fresh', 'latest', 'recent'})

# Bare genre words: "recommend me 5 afrobeats songs" is really a genre
# request, not a song search.  Deliberately conservative — only words that
# are unambiguously genres (never song titles) redirect to a genre pick.
_GENRE_WORDS = frozenset({
    'pop', 'rap', 'hip hop', 'hip-hop', 'hiphop', 'rnb', 'r&b', 'soul',
    'rock', 'country', 'jazz', 'latin', 'reggaeton', 'kpop', 'k-pop',
    'dance', 'electronic', 'edm', 'house', 'techno', 'afrobeats',
    'afrobeat', 'amapiano', 'dancehall', 'reggae', 'gospel', 'classical',
    'metal', 'punk', 'indie', 'folk', 'blues', 'funk', 'disco',
    'lofi', 'lo-fi', 'acoustic',
})

WIKI_KEYWORDS = [
    'wiki', 'wikipedia',
]

ARTIST_KEYWORDS = [
    'who is', 'who are', 'tell me about', 'about the artist',
    'artist info', 'info on', 'biography', 'bio of', 'about .* artist',
]

YOUTUBE_KEYWORDS = [
    'video for', 'music video', 'watch', 'show the video',
    'find the video', 'play', 'youtube',
]

DOWNLOAD_KEYWORDS = [
    'download', 'save video', 'get video', 'download video',
]

MP3_KEYWORDS = [
    'mp3', 'audio', 'convert to mp3', 'convert to audio',
    'extract audio', 'just the audio', 'as mp3',
    'convert.*mp3', 'convert.*audio',
]

TRENDING_KEYWORDS = [
    'trending', 'what.s trending', 'popular', 'top songs',
    'what.s popular', 'hot right now', 'charts', 'top music',
    'what.s hot', 'show trending', 'show popular',
]

TRANSLATE_KEYWORDS = [
    'translate', 'translated', 'translation',
    'arabic', 'in arabic', 'to arabic',
    'spanish', 'to spanish', 'in spanish',
    'french', 'to french', 'in french',
    'german', 'to german', 'in german',
    'italian', 'to italian', 'in italian',
    'portuguese', 'to portuguese',
    'turkish', 'to turkish',
    'russian', 'to russian',
    'japanese', 'to japanese',
    'korean', 'to korean',
    'chinese', 'to chinese',
    'hindi', 'to hindi',
]

ANALYZE_KEYWORDS = [
    'analyze', 'analysis', 'break down', 'breakdown',
    'deep dive', 'detailed analysis',
]

STATS_KEYWORDS = [
    'stats', 'statistics', 'word count', 'how many words',
]

SONG_DASHBOARD_KEYWORDS = [
    'song dashboard', 'full info', 'everything about', 'overview of',
    'all about', 'tell me everything',
]

QUIZ_KEYWORDS = [
    'quiz', 'play a game', 'guess the song', 'lyrics game',
    'start a quiz', 'music quiz',
]

RANDOM_KEYWORDS = [
    'random', 'surprise me', 'random song', 'pick a song',
    'anything', 'something random',
]

THROWBACK_KEYWORDS = [
    'throwback', 'from the 80s', 'from the 90s', 'from the 2000s',
    'from the 2010s', "from the 80's", "from the 90's",
    'nineties', 'eighties', 'oldies', 'classic hits',
    '80s hits', '90s hits', '2000s hits', '2010s hits',
    'take me back', 'back to the',
]


def _extract_decade(text: str) -> str:
    """Map free text to '80s'/'90s'/'2000s'/'2010s'; '' when none found."""
    m = re.search(r'\b(80|90)s\b', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}s"
    m = re.search(r'\b(2000|2010)s\b', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}s"
    m = re.search(r'\b(19[89]\d|20[01]\d)\b', text)
    if m:
        year = int(m.group(1))
        if year < 1990:
            return '80s'
        if year < 2000:
            return '90s'
        if year < 2010:
            return '2000s'
        return '2010s'
    if re.search(r'\bnineties\b', text, re.IGNORECASE):
        return '90s'
    if re.search(r'\beighties\b', text, re.IGNORECASE):
        return '80s'
    return ''


# ── Typo-tolerant song titles (round 5) ────────────────────────────────────
# Local corpus of known song titles used to fuzzy-correct obvious typos
# ("calin down" → "Calm Down"). Only used where the user typed a single
# song phrase (e.g. the translate path), never on "Artist - Song" input.
_LOCAL_TITLES = None  # lower-title -> original title


def _local_song_titles() -> dict:
    global _LOCAL_TITLES
    if _LOCAL_TITLES is None:
        titles = {}
        try:
            from services.artist_service import RANDOM_SONGS_POOL, GENRE_TOP_SONGS
            for p in RANDOM_SONGS_POOL:
                t = (p.get('song') or '').strip()
                if t:
                    titles.setdefault(t.lower(), t)
            for songs in GENRE_TOP_SONGS.values():
                for s in songs:
                    t = (s.get('song') or '').strip()
                    if t:
                        titles.setdefault(t.lower(), t)
        except Exception:
            pass
        try:
            from services.quiz_service import get_quiz_songs
            for s in get_quiz_songs():
                t = (s.get('song') or '').strip()
                if t:
                    titles.setdefault(t.lower(), t)
        except Exception:
            pass
        _LOCAL_TITLES = titles
    return _LOCAL_TITLES


def _fuzzy_correct_title(text: str) -> str:
    """Correct an obvious typo in a bare song phrase; return text unchanged
    when no close local title exists."""
    import difflib
    cleaned = text.strip()
    if not cleaned or len(cleaned.split()) > 6:
        return text
    titles = _local_song_titles()
    if not titles:
        return text
    matches = difflib.get_close_matches(cleaned.lower(), titles.keys(),
                                        n=1, cutoff=0.82)
    if matches and matches[0] != cleaned.lower():
        return titles[matches[0]]
    return text

SUBSCRIBE_KEYWORDS = [
    'subscribe', 'daily songs', 'send me daily', 'daily picks',
]

UNSUBSCRIBE_KEYWORDS = [
    'unsubscribe', 'stop daily', 'no more daily',
]

FILLER_WORDS = [
    'show', 'me', 'find', 'get', 'can', 'you', 'please', 'i', 'want',
    'a', 'this', 'that', 'is', 'give', 'do', 'could', 'would',
    'some', 'the', 'right', 'now', 'songs', 'song', 'music',
]


# ── Mood-word lexicon (round 6 QA) ──────────────────────────────────────────
# Lets inputs like "something happy" or "play happy sad songs" reach the
# /mood feature without the literal word "mood".
MOOD_WORDS = frozenset({
    'happy', 'happier', 'happiest', 'sad', 'sadder', 'saddest',
    'chill', 'chillout', 'chilled', 'angry', 'romantic', 'love',
    'hype', 'hyped', 'calm', 'calmer', 'relaxed', 'relaxing',
    'energetic', 'party', 'workout', 'sleepy', 'melancholy', 'moody',
    'upbeat', 'downbeat', 'feelgood', 'lonely', 'nostalgic', 'nostalgia',
    'emotional', 'dark', 'bright', 'summer', 'winter', 'rainy',
})

# Words allowed alongside mood words in a mood phrase ("something happy").
# Anything else (e.g. "birthday") keeps the song path.
_MOOD_PHRASE_OK = frozenset(FILLER_WORDS) | frozenset({
    'feel', 'feeling', 'feels', 'felt', 'mood', 'moods', 'vibe', 'vibes',
    'tunes', 'tune', 'track', 'tracks', 'playlist', 'mix',
    'something', 'anything',
})

# Explicit framing words: without one of these (or 2+ mood words), a single
# mood word with only generic filler ("find me happier") stays a song
# search — "Happier" is a real song title, and the specific title wins.
_MOOD_FRAMING_WORDS = frozenset({
    'feel', 'feeling', 'feels', 'felt', 'mood', 'moods', 'vibe', 'vibes',
    'tunes', 'tune', 'track', 'tracks', 'playlist', 'mix',
    'something', 'anything',
})


def _extract_mood_word(text: str) -> str:
    """First mood word in the text, or '' when none."""
    for w in re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()):
        if w in MOOD_WORDS:
            return w
    return ''


def _is_mood_phrase(text: str) -> bool:
    """True for inputs that are only mood words + filler ("something happy").

    Guards: needs 2+ words (bare "happy" stays a song lookup — Pharrell),
    explicit "Artist - Song" / "Song by Artist" structure always wins, and
    a single mood word needs an explicit framing word ("something", "feel",
    "vibe", ...) or a second mood word — otherwise "find me happier" is the
    song "Happier", not a mood request.
    """
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower())
    if len(words) < 2 or ' - ' in text:
        return False
    if _BY_SONG_RE.match(text):
        return False
    mood_hits = sum(1 for w in words if w in MOOD_WORDS)
    if mood_hits == 0:
        return False
    if not all(w in MOOD_WORDS or w in _MOOD_PHRASE_OK for w in words):
        return False
    if mood_hits >= 2:
        return True
    return any(w in _MOOD_FRAMING_WORDS for w in words)


def _close_artist(name: str) -> Optional[str]:
    """Canonical artist name for a close local-DB match, else None.

    Stricter than get_artist_info's containment matching: "greedy by tate
    mcrae" must NOT resolve to the Tate McRae card.
    """
    import difflib
    try:
        from services.artist_service import get_artist_info as _gai
        hit = _gai(name)
        if hit and difflib.SequenceMatcher(
                None, name.lower(), hit['name'].lower()).ratio() >= 0.75:
            return hit['name']
    except Exception:
        pass
    return None


def _known_artist(name: str) -> bool:
    """True when the name matches the local artist DB (lazy import)."""
    return _close_artist(name) is not None


def _match_keywords(text: str, keywords: list) -> bool:
    for kw in keywords:
        if re.search(r'\b' + kw + r'\b', text, re.IGNORECASE):
            return True
    return False


def _extract_youtube_url(text: str) -> Optional[str]:
    match = YOUTUBE_URL_PATTERN.search(text)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None


def _extract_query_after(text: str, patterns: list) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            remainder = text[match.end():].strip()
            remainder = re.sub(r'^(for|of|to|the|song)\s+', '', remainder, flags=re.IGNORECASE).strip()
            if remainder:
                return remainder
    return ''


def _normalize_song_query(raw: str) -> str:
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', raw.strip(), re.IGNORECASE)
    if by_match:
        song_part = by_match.group(1).strip()
        artist_part = by_match.group(2).strip()
        # A leading count is not part of the title: "10 hello by adele"
        # must reorder to "adele - hello", not "adele - 10 hello".
        song_part = re.sub(r'^\d{1,2}\s+', '', song_part).strip()
        # Guards: pronouns can never be artists ("stand by me" is not
        # "me - stand"), questions stay with the NLP layer, and generic
        # phrasing is never a song title ("songs to hello by adele" must
        # not become "adele - songs to hello").
        first_word = song_part.split()[0].lower() if song_part.split() else ''
        song_words = set(re.findall(r'[a-z]+', song_part.lower()))
        if (song_part and artist_part
                and len(song_part) >= 2 and len(artist_part) >= 2
                and artist_part.lower() not in _PRONOUNS
                and first_word not in _QUESTION_WORDS
                and not (song_words & _GENERIC_SONG_WORDS)):
            return f"{artist_part} - {song_part}"
    return raw.strip()


def _strip_filler_prefix(text: str) -> str:
    result = text
    while True:
        cleaned = re.sub(
            r'^(for|of|to|the|me|show|find|get|can|you|please|i|want|a|this|that|is|give|do|some|right|now)\s+',
            '', result, flags=re.IGNORECASE
        ).strip()
        if cleaned == result:
            break
        result = cleaned
    return result


def _strip_filler_suffix(text: str) -> str:
    result = text
    while True:
        cleaned = re.sub(
            r'\s+(on|in|at|for|to|please|now|right now)$',
            '', result, flags=re.IGNORECASE
        ).strip()
        if cleaned == result:
            break
        result = cleaned
    return result


def _clean_query(text: str, keywords_to_remove: list) -> str:
    result = text
    for kw in keywords_to_remove:
        result = re.sub(r'\b' + kw + r'\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s+', ' ', result).strip()
    result = _strip_filler_prefix(result)
    result = _strip_filler_suffix(result)
    result = _normalize_song_query(result)
    return result


def _clean_query_translate(text: str) -> str:
    import re as _re
    lang_suffix = ''
    lang_match = _re.search(r'\s+(?:to|into|in)\s+(\w+)\s*$', text, _re.IGNORECASE)
    if lang_match:
        lang_suffix = lang_match.group(0).strip()
        text = text[:lang_match.start()].strip()

    result = text
    for kw in ['translate', 'translated', 'translation', 'can you', 'please', 'i want']:
        result = _re.sub(r'\b' + kw + r'\b', '', result, flags=_re.IGNORECASE)
    result = _re.sub(r'\s+', ' ', result).strip()
    result = _strip_filler_prefix(result)
    result = _strip_filler_suffix(result)
    result = _normalize_song_query(result)

    # Typo tolerance for a bare song phrase ("calin down" → "Calm Down").
    # Only when no artist was given — "Artist - Song" input is never touched.
    if ' - ' not in result and ' – ' not in result:
        result = _fuzzy_correct_title(result)

    if lang_suffix:
        result = f"{result} {lang_suffix}".strip()
    return result


def _extract_top_genre(text: str) -> Optional[str]:
    patterns = [
        r'\btop\s+(\w+)',
        r'\bbest\s+(\w+)',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            genre = match.group(1).lower()
            if genre in ('songs', 'song', 'music', 'tracks'):
                continue
            return genre

    patterns_with_suffix = [
        r'\btop\s+(\w+)\s+(?:songs?|music|tracks?)',
        r'\bbest\s+(\w+)\s+(?:songs?|music|tracks?)',
        r'(?:show|give)\s+(?:me\s+)?top\s+(\w+)',
        r'(?:show|give)\s+(?:me\s+)?best\s+(\w+)',
    ]
    for pat in patterns_with_suffix:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            genre = match.group(1).lower()
            if genre not in ('songs', 'song', 'music', 'tracks', 'the', 'me', 'some'):
                return genre

    return None


def detect_intent(text: str) -> Tuple[Optional[str], str]:
    text = text.strip()

    if not text or text.startswith('/'):
        return None, ''

    # Normalize sloppy typing before any matching: collapse inner whitespace
    # ("BLINDING   LIGHTS") and repeated dashes ("drake--god's plan").
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[-–—]{2,}', '-', text)

    yt_url = _extract_youtube_url(text)
    if yt_url:
        if _match_keywords(text, MP3_KEYWORDS):
            return 'mp3', yt_url
        return 'download', yt_url

    if _match_keywords(text, UNSUBSCRIBE_KEYWORDS):
        return 'unsubscribe', ''

    if _match_keywords(text, SUBSCRIBE_KEYWORDS):
        return 'subscribe', ''

    if _match_keywords(text, QUIZ_KEYWORDS):
        return 'quiz', ''

    if _match_keywords(text, THROWBACK_KEYWORDS):
        decade = _extract_decade(text)
        return 'throwback', decade

    # Decade detected but no throwback keywords ("i want 80s music").
    # Single tokens ("1985") stay on the song path to protect real titles.
    if len(text.split()) >= 2:
        _dec = _extract_decade(text)
        if _dec:
            return 'throwback', _dec

    # Mood-word phrases ("something happy", "i feel sad") → /mood.
    # Runs before the generic keyword scans so the feature is reachable.
    if _is_mood_phrase(text):
        return 'mood', _extract_mood_word(text)

    # "recommend something new" / "suggest fresh music" → fresh releases.
    # Must run BEFORE the random scan: "anything" is a random keyword and
    # would otherwise misroute "recommend anything new" into a broken
    # random query ("recommend new").  Only fires when the cleaned
    # remainder is purely freshness words — "recommend new songs by
    # adele" keeps its artist meaning via the __fresh__ artist: form.
    # (Keyword-stripped manually here, NOT via _clean_query, so the
    # "X by Y" reorder can't mangle "new by adele" first.)
    if _match_keywords(text, RECOMMEND_KEYWORDS):
        _fq = text
        for _fkw in (RECOMMEND_KEYWORDS
                     + ['something', 'anything', 'some', 'me', 'please',
                        'songs', 'song', 'music', 'tracks', 'track',
                        'tunes', 'tune']):
            _fq = re.sub(r'\b' + _fkw + r'\b', '', _fq, flags=re.IGNORECASE)
        _fq = re.sub(r'\s+', ' ', _fq).strip()
        _bfm = re.match(r'^(new|fresh|latest|recent)\s+by\s+(.+)$',
                        _fq, re.IGNORECASE)
        if _bfm and _bfm.group(2).strip():
            return 'recommend', f"__fresh__ artist:{_bfm.group(2).strip()}"
        # "suggest fresh afrobeats" → fresh releases in that genre.
        _fgm = re.match(r'^(new|fresh|latest|recent)\s+(.+)$',
                        _fq, re.IGNORECASE)
        if _fgm and _fgm.group(2).strip().lower() in _GENRE_WORDS:
            return 'recommend', \
                f"__fresh__ genre:{_fgm.group(2).strip().lower()}"
        if _fq and set(_fq.lower().split()) <= _FRESH_WORDS:
            return 'recommend', '__fresh__'

    if _match_keywords(text, RANDOM_KEYWORDS):
        # "random rap", "surprise me with some soul" — keep the trailing
        # genre so natural-language requests stay genre-aware, exactly
        # like /random <genre>.  Bare "random" still yields '' (any genre).
        _genre_q = _clean_query(text, [
            'surprise me', 'pick me a song', 'pick a song',
            'something random', 'anything', 'random',
            'song', 'songs', 'track', 'tracks', 'tune', 'music',
            'something',
            'play me', 'give me', 'play', 'put on', 'show me', 'find me',
            'get me',
        ])
        return 'random', _genre_q

    # "gimme some afrobeats" / "give me some jazz" → genre random pick.
    # Conservative on purpose: only when the remainder is short, carries no
    # other intent's keywords, and has no "by" (the "X by Y" artist pattern
    # is handled by _PLAY_BY_ARTIST_RE / the song branch below).  Anything
    # longer or ambiguous falls through to the normal branches as before.
    _gimme = re.match(r'^(?:gimme|give\s+me)\s+(.+?)[.!?]*$', text,
                      re.IGNORECASE)
    if _gimme and not _PLAY_BY_ARTIST_RE.match(text):
        _g_rest = _strip_filler_prefix(re.sub(
            r'^(some|songs?|music|tracks?|tunes?)\s+', '',
            _gimme.group(1).strip(), flags=re.IGNORECASE))
        _g_words = _g_rest.split()
        _g_low = _g_rest.lower()
        _g_blocked = (LYRICS_KEYWORDS + TRANSLATE_KEYWORDS + YOUTUBE_KEYWORDS
                      + MP3_KEYWORDS + DOWNLOAD_KEYWORDS + QUIZ_KEYWORDS
                      + WIKI_KEYWORDS)
        if (_g_rest and len(_g_words) <= 2
                and not re.search(r'\bby\b', _g_low)
                and not any(k in _g_low for k in _g_blocked)):
            return 'random', _g_rest

    if _match_keywords(text, TRENDING_KEYWORDS):
        genre = _extract_top_genre(text)
        if genre:
            return 'top', genre
        return 'trending', ''

    genre = _extract_top_genre(text)
    if genre:
        return 'top', genre

    if _match_keywords(text, TRANSLATE_KEYWORDS):
        query = _clean_query_translate(text)
        return 'translate', query

    if _match_keywords(text, ANALYZE_KEYWORDS):
        query = _clean_query(text, ['analyze', 'analysis', 'break down', 'breakdown', 'deep dive', 'detailed'])
        return 'analyze', query

    if _match_keywords(text, STATS_KEYWORDS):
        query = _clean_query(text, ['stats', 'statistics', 'word count', 'how many words'])
        return 'stats', query

    if _match_keywords(text, RECOMMEND_KEYWORDS):
        _rec_clean = ['similar', 'songs like', 'music like', 'recommend',
                      'recommendation', 'suggestion', 'suggest',
                      'something like', 'more like', 'like this',
                      'what else', 'similar songs', 'similar music', 'like',
                      # Generic phrasing must go too, otherwise the
                      # "X by Y" reorder mangles it: "songs similar
                      # to hello by adele" → "adele - hello", not
                      # "adele - songs to hello".
                      'songs', 'song', 'music', 'tracks', 'track',
                      'tunes', 'tune']
        # Count FIRST: "recommend 10 songs like hello by adele" must parse
        # the 10 before the "X by Y" reorder runs, or the reorder swallows
        # it ("adele - 10 hello").  Filler goes first so "give me 3 ..."
        # exposes its leading count.
        _bare = text
        for _kw in _rec_clean:
            _bare = re.sub(r'\b' + _kw + r'\b', '', _bare,
                           flags=re.IGNORECASE)
        _bare = re.sub(r'\s+', ' ', _bare).strip()
        _bare = _strip_filler_prefix(_bare)
        _rec_n = 5
        _cm = re.match(r'^(\d{1,2})\s+(.+)$', _bare)
        if _cm:
            _rec_n = max(1, min(int(_cm.group(1)), 10))
            _bare = _cm.group(2).strip()
        query = _clean_query(_bare, [])
        # "3 by taylor swift" → artist mode (the "artist:" prefix forces it
        # in recommend_command, skipping the artist-vs-song question).
        _bym = re.match(r'^by\s+(.+)$', query, re.IGNORECASE)
        if _bym and _bym.group(1).strip():
            _aq = f"artist:{_bym.group(1).strip()}"
            return 'recommend', f"__n{_rec_n}__ {_aq}" if _rec_n != 5 else _aq
        # Bare genre ("recommend me 5 afrobeats songs") is a genre request,
        # not a song search → live genre pick, like /random <genre>.
        if query.lower() in _GENRE_WORDS:
            return 'random', query.lower()
        if _rec_n != 5:
            return 'recommend', f"__n{_rec_n}__ {query}".rstrip()
        return 'recommend', query

    if _match_keywords(text, WIKI_KEYWORDS):
        words = text.strip().split()
        if len(words) >= 2 and words[0].lower() in ('wiki', 'wikipedia'):
            query = ' '.join(words[1:])
            return 'wiki', query

    if _match_keywords(text, ARTIST_KEYWORDS):
        query = _extract_query_after(text, [r'who is\s*', r'who are\s*', r'tell me about\s*',
                                            r'about\s*', r'info on\s*', r'bio of\s*'])
        if not query:
            query = _clean_query(text, ['who', 'is', 'are', 'tell', 'about', 'artist', 'info', 'biography', 'bio'])
        return 'artist', query

    # "play something by X" → artist-based recommend (must precede YouTube scan)
    _play_by = _PLAY_BY_ARTIST_RE.match(text)
    if _play_by:
        artist = _play_by.group(1).strip().rstrip('.')
        return 'recommend', artist

    # "play <song>" / "put on <song>" → song dashboard (embeds the video link).
    # Explicit youtube/video/mp3/audio mentions fall through to the old scans.
    _play_song = _PLAY_SONG_RE.match(text)
    if _play_song:
        _ps = _play_song.group(1).strip()
        if not re.search(r'\b(youtube|video|mp3|audio)\b', _ps, re.IGNORECASE):
            _ps = _strip_filler_suffix(_ps)
            if _ps:
                # "play X by Y" keeps its by-structure as a song query.
                if re.search(r'\bby\b', _ps, re.IGNORECASE):
                    return 'song', _normalize_song_query(_ps)
                # Mood-word soup ("play happy sad songs") → mood mix.
                if _is_mood_phrase(_ps):
                    return 'mood', _extract_mood_word(_ps)
                # Bare known artist ("put on some drake") → artist card.
                _core = re.sub(r'^(some|a)\s+', '', _ps,
                               flags=re.IGNORECASE).strip()
                _artist_hit = _close_artist(_core) if _core else None
                if _artist_hit:
                    return 'artist', _artist_hit
                # Generic filler ("play some music") → surprise them.
                if not _core or _core.lower() in _GENERIC_SONG_WORDS:
                    return 'random', ''
                return 'song', _normalize_song_query(_ps)

    if _match_keywords(text, YOUTUBE_KEYWORDS):
        query = _clean_query(text, ['video', 'music video', 'watch', 'play', 'youtube',
                                     'show', 'find'])
        return 'youtube', query

    if _match_keywords(text, SONG_DASHBOARD_KEYWORDS):
        query = _clean_query(text, ['song dashboard', 'full info', 'everything about',
                                     'overview', 'all about', 'tell', 'everything'])
        return 'song', query

    if _match_keywords(text, LYRICS_KEYWORDS):
        query = _clean_query(text, ['lyrics', 'lyric', 'words', 'text', 'sing',
                                     'how does', 'go', 'gimme', 'give me'])
        return 'lyrics', query

    if _match_keywords(text, MP3_KEYWORDS):
        query = _clean_query(text, ['convert', 'extract', 'just', 'the', 'as', 'mp3', 'audio'])
        return 'mp3', query

    if _match_keywords(text, DOWNLOAD_KEYWORDS):
        query = _clean_query(text, ['download', 'save', 'get'])
        return 'download', query

    # "who sings/sang <song>" → the artist is the answer; the song dashboard
    # shows it front and center.
    for _rx in (_WHO_SINGS_RE, _WHO_SANG_RE):
        _m = _rx.match(text)
        if _m:
            _q = _m.group(1).strip().strip('"').strip("'").strip()
            if _q:
                return 'song', _q

    # "that song that goes <lyrics fragment>" → search by the fragment.
    _ts = _THAT_SONG_RE.match(text)
    if _ts:
        _frag = _ts.group(1).strip().strip('"').strip("'").strip()
        if _frag:
            return 'song', _frag

    # "find/show/get/give me <X>" → artist when we know them, else a song.
    _fm = _FIND_ME_RE.match(text)
    if _fm:
        _rest = _strip_filler_suffix(_fm.group(1).strip())
        if _rest:
            try:
                from services.artist_service import get_artist_info as _gai
                if _gai(_rest):
                    return 'artist', _rest
            except Exception:
                pass
            return 'song', _rest

    # "Artist - Song" explicit structured format (last resort before NLP).
    # Catches inputs like "Gemini - Hola", "Radiohead - Creep", etc.
    # Both sides must be ≥2 characters to avoid matching partial/accidental dashes.
    # No keyword-matching needed — if it looks like a clean pair, treat as /song.
    _art_song = _ARTIST_SONG_RE.match(text)
    if _art_song:
        part_a = _art_song.group(1).strip()
        part_b = _art_song.group(2).strip()
        if len(part_a) >= 2 and len(part_b) >= 2:
            return 'song', f"{part_a} - {part_b}"

    # "Song by Artist" free-form pattern (no keyword needed).
    # Catches inputs like "water by tyla" or "blinding lights by the weeknd".
    # Runs AFTER the dash-pair check so an explicit "Artist - Song" wins,
    # and after all keyword checks so "play X by Y" style intents keep priority.
    # Questions ("what song by adele?") and pronoun artists ("stand by me")
    # are left for the NLP layer, which understands them better.
    if '?' not in text:
        _by_match = _BY_SONG_RE.match(text)
        if _by_match:
            _song_part = _by_match.group(1).strip()
            _artist_part = _by_match.group(2).strip()
            _first_word = _song_part.split()[0].lower() if _song_part.split() else ''
            if (len(_song_part) >= 2 and len(_artist_part) >= 2
                    and _first_word not in _QUESTION_WORDS
                    and _artist_part.lower() not in _PRONOUNS):
                if _song_part.lower() in _GENERIC_SONG_WORDS:
                    return 'recommend', _artist_part
                return 'song', f"{_artist_part} - {_song_part}"

    return None, text
