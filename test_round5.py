"""Round 5 tests:
Job 1 — /random display canonicalization (exactly one clean "Artist - Song").
Job 2 — natural-language input upgrade (40+ phrasings).
Run: python test_round5.py   (no Telegram network needed)
"""
import sys
sys.path.insert(0, '/home/hatch/workspace/lyrics-master/repo')

from intent_router import detect_intent
from services.lyrics_service import canonicalize_track_names

passed = failed = 0

def check(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {name}\n    expected: {expected!r}\n    actual:   {actual!r}")

print("== Job 1: canonicalize_track_names ==")
canon_cases = [
    # the reported bug
    (('Rod Wave', 'Rod Wave - Dope Girl (Official Audio)'), ('Rod Wave', 'Dope Girl')),
    # doubled artist, various suffixes / separators
    (('U2', 'U2 - With Or Without You (Official Music Video)'), ('U2', 'With Or Without You')),
    (('Tyla', 'Tyla - Water [Official Video]'), ('Tyla', 'Water')),
    (('Adele', 'Adele - Hello (Official Video)'), ('Adele', 'Hello')),
    (('Drake', 'Drake - God\'s Plan (Official Audio)'), ('Drake', 'God\'s Plan')),
    (('Ed Sheeran', 'Ed Sheeran - Shape of You (Lyric Video)'), ('Ed Sheeran', 'Shape of You')),
    (('Queen', 'Queen – Bohemian Rhapsody (Official Video)'), ('Queen', 'Bohemian Rhapsody')),
    (('Beyonce', 'Beyonce - Halo - Official Music Video'), ('Beyonce', 'Halo')),
    # case-insensitive dedupe
    (('rod wave', 'ROD WAVE - Dope Girl'), ('rod wave', 'Dope Girl')),
    (('tyla', 'TYLA - WATER (OFFICIAL AUDIO)'), ('tyla', 'WATER')),
    # bare prefix without separator
    (('Rod Wave', 'Rod Wave Dope Girl'), ('Rod Wave', 'Dope Girl')),
    # suffix only, no doubling
    (('Adele', 'Hello (Official Video)'), ('Adele', 'Hello')),
    (('SZA', 'Kill Bill (Audio)'), ('SZA', 'Kill Bill')),
    (('The Weeknd', 'Blinding Lights [Official Video]'), ('The Weeknd', 'Blinding Lights')),
    # must NOT touch
    (('Adele', 'Hello'), ('Adele', 'Hello')),
    (('Drake', 'God\'s Plan'), ('Drake', 'God\'s Plan')),
    (('Morgan Wallen', 'Last Thing You Need (from GTAVI: The Album)'),
     ('Morgan Wallen', 'Last Thing You Need (from GTAVI: The Album)')),
    (('Kendrick Lamar', 'LOVE. (feat. Zacari)'), ('Kendrick Lamar', 'LOVE. (feat. Zacari)')),
    (('Eminem', 'Lose Yourself (8 Mile Soundtrack)'), ('Eminem', 'Lose Yourself (8 Mile Soundtrack)')),
    # whitespace normalization
    (('  Adele  ', '  Hello   (Official Audio) '), ('Adele', 'Hello')),
    (('Rod Wave', 'Rod Wave  -  Dope Girl'), ('Rod Wave', 'Dope Girl')),
    # empty-safe
    (('', ''), ('', '')),
    (('Adele', ''), ('Adele', '')),
]
for (a, s), expected in canon_cases:
    check(f"canon({a!r}, {s!r})", canonicalize_track_names(a, s), expected)

# The full random display pipeline: pool names -> (mocked) doubled API result
# -> display string must be exactly "Artist - Song".
def random_display(artist_name, song_name, api_artist, api_track):
    artist, song = canonicalize_track_names(api_artist, api_track)
    return f"{artist} - {song}" if artist and song else (artist or song or f"{artist_name} - {song_name}")

check("random display (bug case)",
      random_display('Rod Wave', 'Dope Girl', 'Rod Wave', 'Rod Wave - Dope Girl (Official Audio)'),
      'Rod Wave - Dope Girl')
check("random display (clean case)",
      random_display('Tyla', 'Water', 'Tyla', 'Water'),
      'Tyla - Water')

print("== Job 2: detect_intent (40+ phrasings) ==")
nl_cases = [
    # required examples
    ("Water by tyla", 'song', 'tyla - Water'),
    ("play despacito", 'song', 'despacito'),
    ("lyrics for someone like you by adele", 'lyrics', 'adele - someone like you'),
    ("adele hello lyrics", 'lyrics', 'adele hello'),
    ("who sings calm down", 'song', 'calm down'),
    ("songs by taylor swift", 'recommend', 'taylor swift'),
    ("find me happier", 'song', 'happier'),
    ("show me bruno mars", 'artist', 'bruno mars'),
    ("i want the lyrics of drivers license", 'lyrics', 'drivers license'),
    ("can you play blinding lights", 'song', 'blinding lights'),
    ("that song that goes never gonna give you up", 'song', 'never gonna give you up'),
    ("recommend something like As It Was", 'recommend', 'As It Was'),
    ("analyze vampire by olivia rodrigo", 'analyze', 'olivia rodrigo - vampire'),
    ("translate calin down to arabic", 'translate', 'Calm Down to arabic'),
    ("quiz me", 'quiz', ''),
    ("surprise me", 'random', ''),
    ("something from the 90s", 'throwback', '90s'),
    # ambiguous query stays untouched (artist-or-song prompt path)
    ("rush", None, 'rush'),
    # separator path unchanged
    ("Gemini - Hola", 'song', 'Gemini - Hola'),
    ("Adele - Hello", 'song', 'Adele - Hello'),
    # play variants
    ("play blinding lights", 'song', 'blinding lights'),
    ("put on levitating", 'song', 'levitating'),
    ("can you play shape of you", 'song', 'shape of you'),
    ("please play despacito", 'song', 'despacito'),
    ("play something by adele", 'recommend', 'adele'),
    ("give me songs by taylor swift", 'recommend', 'taylor swift'),
    ("play despacito on youtube", 'youtube', 'despacito'),
    # who sings variants
    ("who sang bohemian rhapsody", 'song', 'bohemian rhapsody'),
    ("who sings hello", 'song', 'hello'),
    # find/show/get me variants
    ("show me the weeknd", 'artist', 'the weeknd'),
    ("get me levitating", 'song', 'levitating'),
    ("find me taylor swift", 'artist', 'taylor swift'),
    ("show me adele", 'artist', 'adele'),
    ("find me calm down", 'song', 'calm down'),
    # that-song variants
    ("the song that goes hello from the other side", 'song', 'hello from the other side'),
    # recommend variants
    ("something like circles", 'recommend', 'circles'),
    ("recommend music like blinding lights", 'recommend', 'blinding lights'),
    # analyze variants
    ("analyze olivia rodrigo - vampire", 'analyze', 'olivia rodrigo - vampire'),
    # translate variants
    ("translate calm down to arabic", 'translate', 'calm down to arabic'),
    ("translate despacito to english", 'translate', 'despacito to english'),
    # quiz/random variants
    ("start a quiz", 'quiz', ''),
    ("something random", 'random', ''),
    # throwback variants
    ("play some 80s hits", 'throwback', '80s'),
    ("take me back to the 2000s", 'throwback', '2000s'),
    ("throwback 90s", 'throwback', '90s'),
    ("something from the 80s", 'throwback', '80s'),
    # pre-existing behaviors that must not regress
    ("trending now", 'trending', ''),
    ("top afrobeats", 'top', 'afrobeats'),
    ("tell me about adele", 'artist', 'adele'),
    ("who is the weeknd", 'artist', 'weeknd'),
    ("blinding lights by the weeknd", 'song', 'the weeknd - blinding lights'),
    ("music by drake", 'recommend', 'drake'),
]
for text, exp_intent, exp_query in nl_cases:
    intent, query = detect_intent(text)
    check(f"intent({text!r})", (intent, query), (exp_intent, exp_query))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
