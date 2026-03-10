import logging
import requests
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'LyricsMasterBot/1.0 (Telegram music bot; educational project)'
})

ARTIST_DATABASE = {
    'tyla': {'name': 'Tyla', 'genre': 'Afrobeats / Amapiano', 'debut': 2019, 'country': 'South Africa',
             'top_songs': ['Water', 'Truth or Dare', 'Jump', 'ART', 'Getting Late']},
    'rema': {'name': 'Rema', 'genre': 'Afrobeats / Afro-rave', 'debut': 2019, 'country': 'Nigeria',
             'top_songs': ['Calm Down', 'Soundgasm', 'Selense', 'Charm', 'Rave & Roses']},
    'burna boy': {'name': 'Burna Boy', 'genre': 'Afrobeats / Afro-fusion', 'debut': 2012, 'country': 'Nigeria',
                  'top_songs': ['Last Last', 'Ye', 'On the Low', 'Anybody', 'City Boys']},
    'wizkid': {'name': 'Wizkid', 'genre': 'Afrobeats', 'debut': 2009, 'country': 'Nigeria',
               'top_songs': ['Essence', 'Ojuelegba', 'Come Closer', 'Joro', 'Soco']},
    'taylor swift': {'name': 'Taylor Swift', 'genre': 'Pop / Country', 'debut': 2006, 'country': 'USA',
                     'top_songs': ['Shake It Off', 'Love Story', 'Blank Space', 'Anti-Hero', 'Cruel Summer']},
    'ed sheeran': {'name': 'Ed Sheeran', 'genre': 'Pop / Folk', 'debut': 2011, 'country': 'UK',
                   'top_songs': ['Shape of You', 'Perfect', 'Thinking Out Loud', 'Photograph', 'Bad Habits']},
    'adele': {'name': 'Adele', 'genre': 'Pop / Soul', 'debut': 2008, 'country': 'UK',
              'top_songs': ['Rolling in the Deep', 'Hello', 'Someone Like You', 'Easy On Me', 'Set Fire to the Rain']},
    'drake': {'name': 'Drake', 'genre': 'Hip-Hop / R&B', 'debut': 2006, 'country': 'Canada',
              'top_songs': ['Hotline Bling', "God's Plan", 'One Dance', 'In My Feelings', 'Started From the Bottom']},
    'the weeknd': {'name': 'The Weeknd', 'genre': 'R&B / Synth-pop', 'debut': 2010, 'country': 'Canada',
                   'top_songs': ['Blinding Lights', 'Starboy', 'Save Your Tears', 'The Hills', 'Die For You']},
    'billie eilish': {'name': 'Billie Eilish', 'genre': 'Pop / Alternative', 'debut': 2015, 'country': 'USA',
                      'top_songs': ['bad guy', 'Happier Than Ever', 'Lovely', 'Therefore I Am', 'Birds of a Feather']},
    'dua lipa': {'name': 'Dua Lipa', 'genre': 'Pop / Dance', 'debut': 2015, 'country': 'UK',
                 'top_songs': ['Levitating', "Don't Start Now", 'New Rules', 'One Kiss', 'Physical']},
    'harry styles': {'name': 'Harry Styles', 'genre': 'Pop / Rock', 'debut': 2010, 'country': 'UK',
                     'top_songs': ['As It Was', 'Watermelon Sugar', 'Adore You', 'Sign of the Times', 'Late Night Talking']},
    'ariana grande': {'name': 'Ariana Grande', 'genre': 'Pop / R&B', 'debut': 2013, 'country': 'USA',
                      'top_songs': ['thank u, next', '7 rings', 'positions', 'no tears left to cry', 'Side to Side']},
    'sza': {'name': 'SZA', 'genre': 'R&B / Neo-Soul', 'debut': 2012, 'country': 'USA',
            'top_songs': ['Kill Bill', 'Good Days', 'Kiss Me More', 'Snooze', 'Love Galore']},
    'kendrick lamar': {'name': 'Kendrick Lamar', 'genre': 'Hip-Hop / Conscious Rap', 'debut': 2004, 'country': 'USA',
                       'top_songs': ['HUMBLE.', 'Alright', 'DNA.', 'Swimming Pools', 'Money Trees']},
    'beyonce': {'name': 'Beyoncé', 'genre': 'R&B / Pop', 'debut': 1997, 'country': 'USA',
                'top_songs': ['Halo', 'Crazy in Love', 'Single Ladies', 'Formation', 'BREAK MY SOUL']},
    'bruno mars': {'name': 'Bruno Mars', 'genre': 'Pop / Funk', 'debut': 2010, 'country': 'USA',
                   'top_songs': ['Just the Way You Are', 'Uptown Funk', 'Grenade', '24K Magic', 'That\'s What I Like']},
    'post malone': {'name': 'Post Malone', 'genre': 'Hip-Hop / Pop', 'debut': 2015, 'country': 'USA',
                    'top_songs': ['Circles', 'Sunflower', 'Rockstar', 'Congratulations', 'White Iverson']},
    'olivia rodrigo': {'name': 'Olivia Rodrigo', 'genre': 'Pop / Alt-Rock', 'debut': 2021, 'country': 'USA',
                       'top_songs': ['drivers license', 'good 4 u', 'vampire', 'deja vu', 'traitor']},
    'bad bunny': {'name': 'Bad Bunny', 'genre': 'Reggaeton / Latin Trap', 'debut': 2016, 'country': 'Puerto Rico',
                  'top_songs': ['Titi Me Preguntó', 'Dakiti', 'Yonaguni', 'Me Porto Bonito', 'Moscow Mule']},
    'eminem': {'name': 'Eminem', 'genre': 'Hip-Hop / Rap', 'debut': 1996, 'country': 'USA',
               'top_songs': ['Lose Yourself', 'Stan', 'Without Me', 'The Real Slim Shady', 'Not Afraid']},
    'rihanna': {'name': 'Rihanna', 'genre': 'Pop / R&B', 'debut': 2005, 'country': 'Barbados',
                'top_songs': ['Umbrella', 'Diamonds', 'We Found Love', 'Work', 'Stay']},
    'coldplay': {'name': 'Coldplay', 'genre': 'Rock / Pop', 'debut': 1996, 'country': 'UK',
                 'top_songs': ['Yellow', 'Fix You', 'Viva la Vida', 'The Scientist', 'Something Just Like This']},
    'imagine dragons': {'name': 'Imagine Dragons', 'genre': 'Pop Rock / Alternative', 'debut': 2008, 'country': 'USA',
                        'top_songs': ['Believer', 'Radioactive', 'Demons', 'Thunder', 'Whatever It Takes']},
    'miley cyrus': {'name': 'Miley Cyrus', 'genre': 'Pop / Rock', 'debut': 2006, 'country': 'USA',
                    'top_songs': ['Flowers', 'Wrecking Ball', 'Party in the U.S.A.', 'Midnight Sky', 'We Can\'t Stop']},
    'lana del rey': {'name': 'Lana Del Rey', 'genre': 'Indie Pop / Baroque Pop', 'debut': 2010, 'country': 'USA',
                     'top_songs': ['Summertime Sadness', 'Young and Beautiful', 'Born to Die', 'Video Games', 'West Coast']},
    'travis scott': {'name': 'Travis Scott', 'genre': 'Hip-Hop / Trap', 'debut': 2012, 'country': 'USA',
                     'top_songs': ['SICKO MODE', 'goosebumps', 'HIGHEST IN THE ROOM', 'Antidote', 'FE!N']},
    'ayra starr': {'name': 'Ayra Starr', 'genre': 'Afrobeats / Afro-pop', 'debut': 2020, 'country': 'Nigeria',
                   'top_songs': ['Rush', 'Sability', 'Bloody Samaritan', 'Last Heartbreak Song', '19 & Dangerous']},
    'tems': {'name': 'Tems', 'genre': 'Afrobeats / R&B', 'debut': 2018, 'country': 'Nigeria',
             'top_songs': ['Free Mind', 'Essence', 'Higher', 'Me & U', 'Love Me JeJe']},
    'fireboy dml': {'name': 'Fireboy DML', 'genre': 'Afrobeats / Afro-pop', 'debut': 2018, 'country': 'Nigeria',
                    'top_songs': ['Peru', 'Jealous', 'Vibration', 'Playboy', 'Bandana']},
}

TRENDING_SONGS = [
    {'artist': 'Kendrick Lamar', 'song': 'Not Like Us', 'note': 'Viral hip-hop anthem'},
    {'artist': 'Sabrina Carpenter', 'song': 'Espresso', 'note': 'Global pop hit'},
    {'artist': 'Billie Eilish', 'song': 'Birds of a Feather', 'note': 'Chart-topping single'},
    {'artist': 'Chappell Roan', 'song': 'Good Luck, Babe!', 'note': 'Breakout pop hit'},
    {'artist': 'Tyla', 'song': 'Water', 'note': 'Amapiano crossover smash'},
    {'artist': 'Shaboozey', 'song': 'A Bar Song (Tipsy)', 'note': 'Country-pop crossover'},
    {'artist': 'SZA', 'song': 'Saturn', 'note': 'R&B with introspective depth'},
    {'artist': 'Doja Cat', 'song': 'Paint The Town Red', 'note': 'Bold pop/rap energy'},
    {'artist': 'Teddy Swims', 'song': 'Lose Control', 'note': 'Soulful vocal powerhouse'},
    {'artist': 'Benson Boone', 'song': 'Beautiful Things', 'note': 'Emotional pop ballad'},
]

GENRE_TOP_SONGS = {
    'afrobeats': [
        {'artist': 'Tyla', 'song': 'Water', 'note': 'Amapiano crossover smash'},
        {'artist': 'Rema', 'song': 'Calm Down', 'note': 'Global Afrobeats anthem'},
        {'artist': 'Burna Boy', 'song': 'Last Last', 'note': 'Afro-fusion hit'},
        {'artist': 'Wizkid', 'song': 'Essence', 'note': 'Smooth Afrobeats classic'},
        {'artist': 'Ayra Starr', 'song': 'Rush', 'note': 'Afro-pop breakout hit'},
        {'artist': 'CKay', 'song': 'Love Nwantiti', 'note': 'TikTok viral sensation'},
        {'artist': 'Fireboy DML', 'song': 'Peru', 'note': 'Catchy Afrobeats banger'},
        {'artist': 'Tems', 'song': 'Free Mind', 'note': 'Soulful Afrobeats R&B'},
        {'artist': 'Asake', 'song': 'Joha', 'note': 'Amapiano street anthem'},
        {'artist': 'Omah Lay', 'song': 'Understand', 'note': 'Afro-fusion gem'},
    ],
    'pop': [
        {'artist': 'Sabrina Carpenter', 'song': 'Espresso', 'note': 'Global pop phenomenon'},
        {'artist': 'Dua Lipa', 'song': 'Levitating', 'note': 'Infectious disco-pop'},
        {'artist': 'Harry Styles', 'song': 'As It Was', 'note': 'Synth-pop earworm'},
        {'artist': 'Olivia Rodrigo', 'song': 'vampire', 'note': 'Emotional pop-rock'},
        {'artist': 'Miley Cyrus', 'song': 'Flowers', 'note': 'Empowerment anthem'},
        {'artist': 'Billie Eilish', 'song': 'Birds of a Feather', 'note': 'Dreamy pop gem'},
        {'artist': 'Chappell Roan', 'song': 'Good Luck, Babe!', 'note': 'Breakout pop hit'},
        {'artist': 'Taylor Swift', 'song': 'Anti-Hero', 'note': 'Self-aware pop classic'},
        {'artist': 'Ariana Grande', 'song': 'yes, and?', 'note': 'Dance-pop confidence'},
        {'artist': 'Bruno Mars', 'song': 'APT.', 'note': 'K-pop crossover hit'},
    ],
    'rap': [
        {'artist': 'Kendrick Lamar', 'song': 'Not Like Us', 'note': 'Viral diss track anthem'},
        {'artist': 'Travis Scott', 'song': 'FE!N', 'note': 'High-energy trap banger'},
        {'artist': 'Drake', 'song': 'Rich Baby Daddy', 'note': 'Smooth hip-hop flow'},
        {'artist': 'J. Cole', 'song': 'No Role Modelz', 'note': 'Conscious rap classic'},
        {'artist': 'Eminem', 'song': 'Houdini', 'note': 'Comeback lyrical showcase'},
        {'artist': 'Megan Thee Stallion', 'song': 'BOA', 'note': 'Bold rap energy'},
        {'artist': 'Future', 'song': 'Type Shit', 'note': 'Trap with attitude'},
        {'artist': '21 Savage', 'song': 'redrum', 'note': 'Dark storytelling rap'},
        {'artist': 'Tyler, The Creator', 'song': 'NOID', 'note': 'Creative hip-hop artistry'},
        {'artist': 'JID', 'song': 'Surround Sound', 'note': 'Technical lyrical skill'},
    ],
    'rnb': [
        {'artist': 'SZA', 'song': 'Saturn', 'note': 'Introspective R&B depth'},
        {'artist': 'The Weeknd', 'song': 'Die For You', 'note': 'Synth R&B with emotion'},
        {'artist': 'Daniel Caesar', 'song': 'Best Part', 'note': 'Silky R&B duet'},
        {'artist': 'Brent Faiyaz', 'song': 'WY@', 'note': 'Moody alternative R&B'},
        {'artist': 'Summer Walker', 'song': 'Playing Games', 'note': 'Vulnerable songwriting'},
        {'artist': 'Khalid', 'song': 'Young Dumb & Broke', 'note': 'Smooth R&B vibes'},
        {'artist': 'Frank Ocean', 'song': 'Nights', 'note': 'Alt-R&B masterpiece'},
        {'artist': 'H.E.R.', 'song': 'Best Part', 'note': 'Soulful contemporary R&B'},
        {'artist': 'Teddy Swims', 'song': 'Lose Control', 'note': 'Soulful vocal power'},
        {'artist': 'Benson Boone', 'song': 'Beautiful Things', 'note': 'Emotional ballad'},
    ],
    'rock': [
        {'artist': 'Arctic Monkeys', 'song': 'Do I Wanna Know?', 'note': 'Dark indie rock'},
        {'artist': 'Imagine Dragons', 'song': 'Believer', 'note': 'Anthemic pop-rock'},
        {'artist': 'Foo Fighters', 'song': 'Everlong', 'note': 'Timeless alt-rock'},
        {'artist': 'The Killers', 'song': 'Mr. Brightside', 'note': 'Iconic indie anthem'},
        {'artist': 'Coldplay', 'song': 'Fix You', 'note': 'Emotional rock ballad'},
        {'artist': 'Twenty One Pilots', 'song': 'Stressed Out', 'note': 'Genre-blending hit'},
        {'artist': 'Green Day', 'song': 'Basket Case', 'note': 'Punk rock classic'},
        {'artist': 'Nirvana', 'song': 'Smells Like Teen Spirit', 'note': 'Grunge anthem'},
        {'artist': 'Muse', 'song': 'Uprising', 'note': 'Epic stadium rock'},
        {'artist': 'Radiohead', 'song': 'Creep', 'note': 'Alt-rock masterpiece'},
    ],
    'latin': [
        {'artist': 'Bad Bunny', 'song': 'Titi Me Pregunto', 'note': 'Reggaeton anthem'},
        {'artist': 'Karol G', 'song': 'BICHOTA', 'note': 'Latin pop empowerment'},
        {'artist': 'Rauw Alejandro', 'song': 'Todo de Ti', 'note': 'Modern Latin pop'},
        {'artist': 'Rosalia', 'song': 'DESPECHA', 'note': 'Spanish pop innovation'},
        {'artist': 'Shakira', 'song': 'Bzrp Music Sessions 53', 'note': 'Viral Latin hit'},
        {'artist': 'Ozuna', 'song': 'Taki Taki', 'note': 'Reggaeton collab banger'},
        {'artist': 'J Balvin', 'song': 'Mi Gente', 'note': 'Global Latin crossover'},
        {'artist': 'Daddy Yankee', 'song': 'Gasolina', 'note': 'Reggaeton classic'},
    ],
    'country': [
        {'artist': 'Shaboozey', 'song': 'A Bar Song (Tipsy)', 'note': 'Country-pop crossover'},
        {'artist': 'Morgan Wallen', 'song': 'Last Night', 'note': 'Country chart-topper'},
        {'artist': 'Luke Combs', 'song': 'Fast Car', 'note': 'Country reimagining'},
        {'artist': 'Zach Bryan', 'song': 'Something in the Orange', 'note': 'Heartfelt country'},
        {'artist': 'Chris Stapleton', 'song': 'Tennessee Whiskey', 'note': 'Country soul anthem'},
        {'artist': 'Beyonce', 'song': 'Texas Hold Em', 'note': 'Country genre crossover'},
        {'artist': 'Post Malone', 'song': 'I Had Some Help', 'note': 'Country-pop fusion'},
    ],
    'kpop': [
        {'artist': 'BTS', 'song': 'Dynamite', 'note': 'Global K-pop phenomenon'},
        {'artist': 'BLACKPINK', 'song': 'How You Like That', 'note': 'K-pop powerhouse'},
        {'artist': 'Stray Kids', 'song': 'LALALALA', 'note': 'High-energy K-pop'},
        {'artist': 'NewJeans', 'song': 'Super Shy', 'note': 'Fresh K-pop sound'},
        {'artist': 'aespa', 'song': 'Supernova', 'note': 'Futuristic K-pop'},
        {'artist': 'SEVENTEEN', 'song': 'Super', 'note': 'K-pop synchronization'},
        {'artist': 'IVE', 'song': 'I AM', 'note': 'Catchy K-pop anthem'},
    ],
}

GENRE_ALIASES = {
    'hiphop': 'rap', 'hip-hop': 'rap', 'hip hop': 'rap', 'trap': 'rap',
    'r&b': 'rnb', 'r and b': 'rnb', 'soul': 'rnb',
    'afro': 'afrobeats', 'amapiano': 'afrobeats', 'afropop': 'afrobeats',
    'reggaeton': 'latin', 'spanish': 'latin', 'latino': 'latin',
    'k-pop': 'kpop', 'korean': 'kpop',
    'alternative': 'rock', 'indie': 'rock', 'punk': 'rock', 'metal': 'rock',
    'classic rock': 'rock', 'classic': 'rock',
}

RANDOM_SONGS_POOL = [
    {'artist': 'Tyla', 'song': 'Water'},
    {'artist': 'Rema', 'song': 'Calm Down'},
    {'artist': 'Billie Eilish', 'song': 'Birds of a Feather'},
    {'artist': 'SZA', 'song': 'Kill Bill'},
    {'artist': 'Kendrick Lamar', 'song': 'HUMBLE.'},
    {'artist': 'Dua Lipa', 'song': 'Levitating'},
    {'artist': 'The Weeknd', 'song': 'Blinding Lights'},
    {'artist': 'Harry Styles', 'song': 'As It Was'},
    {'artist': 'Olivia Rodrigo', 'song': 'drivers license'},
    {'artist': 'Arctic Monkeys', 'song': 'Do I Wanna Know?'},
    {'artist': 'Adele', 'song': 'Hello'},
    {'artist': 'Ed Sheeran', 'song': 'Shape of You'},
    {'artist': 'Bruno Mars', 'song': 'Just the Way You Are'},
    {'artist': 'Eminem', 'song': 'Lose Yourself'},
    {'artist': 'Taylor Swift', 'song': 'Love Story'},
    {'artist': 'Drake', 'song': "God's Plan"},
    {'artist': 'Post Malone', 'song': 'Circles'},
    {'artist': 'Ariana Grande', 'song': 'thank u, next'},
    {'artist': 'Bad Bunny', 'song': 'Dakiti'},
    {'artist': 'Beyonce', 'song': 'Halo'},
    {'artist': 'Coldplay', 'song': 'Yellow'},
    {'artist': 'Imagine Dragons', 'song': 'Believer'},
    {'artist': 'Miley Cyrus', 'song': 'Flowers'},
    {'artist': 'Lana Del Rey', 'song': 'Summertime Sadness'},
    {'artist': 'Travis Scott', 'song': 'SICKO MODE'},
    {'artist': 'Burna Boy', 'song': 'Last Last'},
    {'artist': 'Sabrina Carpenter', 'song': 'Espresso'},
    {'artist': 'Frank Ocean', 'song': 'Nights'},
    {'artist': 'Fleetwood Mac', 'song': 'Dreams'},
    {'artist': 'Queen', 'song': 'Bohemian Rhapsody'},
]


def get_top_by_genre(genre_query: str) -> Optional[tuple]:
    genre_lower = genre_query.lower().strip()
    resolved = GENRE_ALIASES.get(genre_lower, genre_lower)

    if resolved in GENRE_TOP_SONGS:
        songs = list(GENRE_TOP_SONGS[resolved])
        import random as rng
        rng.shuffle(songs)
        return resolved, songs[:7]

    return None


def format_top_songs(genre: str, songs: List[Dict]) -> str:
    genre_emojis = {
        'afrobeats': '🌍', 'pop': '🎤', 'rap': '🎙️', 'rnb': '💜',
        'rock': '🎸', 'latin': '💃', 'country': '🤠', 'kpop': '🇰🇷',
    }
    emoji = genre_emojis.get(genre, '🎵')
    display_genre = genre.upper() if genre in ('rnb', 'kpop') else genre.title()

    lines = []
    rank_emojis = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
    for i, song in enumerate(songs):
        rank = rank_emojis[i] if i < len(rank_emojis) else '🎵'
        lines.append(f"{rank} {song['artist']} — {song['song']}\n   ↳ {song['note']}")

    body = '\n\n'.join(lines)

    return (
        f"{emoji} Top {display_genre}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎤 /lyrics to see any song's lyrics\n"
        "🎵 /song for a full song dashboard"
    )


def get_available_genres() -> List[str]:
    genres = list(GENRE_TOP_SONGS.keys())
    return genres


def get_random_song() -> Dict:
    import random as rng
    return rng.choice(RANDOM_SONGS_POOL)


def get_artist_info(name: str) -> Optional[Dict]:
    name_lower = name.lower().strip()

    if name_lower in ARTIST_DATABASE:
        return ARTIST_DATABASE[name_lower]

    for key, data in ARTIST_DATABASE.items():
        if name_lower in key or key in name_lower:
            return data

    for key, data in ARTIST_DATABASE.items():
        if any(part in key for part in name_lower.split()):
            return data

    return None


def format_artist_info(info: Dict) -> str:
    songs_list = '\n'.join(f"  • {s}" for s in info['top_songs'][:5])
    name_slug = info['name'].replace(' ', '+')
    wiki_url = f"https://en.wikipedia.org/wiki/{info['name'].replace(' ', '_')}"
    yt_url = f"https://www.youtube.com/results?search_query={name_slug}+official"

    return (
        f"🎤 {info['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎵 Genre: {info['genre']}\n"
        f"📅 Debut: {info['debut']}\n"
        f"🌍 From: {info['country']}\n\n"
        f"🔥 Top Songs:\n{songs_list}\n\n"
        f"🔗 Links:\n"
        f"  📚 {wiki_url}\n"
        f"  🎬 {yt_url}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎤 /lyrics {info['top_songs'][0]} to see lyrics\n"
        f"🎵 /song {info['name']} {info['top_songs'][0]} for full dashboard"
    )


def get_trending_songs() -> List[Dict]:
    import random
    pool = list(TRENDING_SONGS)
    random.shuffle(pool)
    return pool[:5]


def format_trending(songs: List[Dict]) -> str:
    lines = []
    emojis = ['🔥', '✨', '💫', '🎶', '⭐']
    for i, song in enumerate(songs):
        emoji = emojis[i] if i < len(emojis) else '🎵'
        lines.append(f"{emoji} {song['artist']} — {song['song']}\n   ↳ {song['note']}")

    body = '\n\n'.join(lines)

    return (
        "📈 Trending Now\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎤 /lyrics to see any song's lyrics\n"
        "🎵 /recommend for similar songs"
    )
