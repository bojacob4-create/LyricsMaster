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

    return (
        f"🎤 {info['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎵 Genre: {info['genre']}\n"
        f"📅 Debut: {info['debut']}\n"
        f"🌍 From: {info['country']}\n\n"
        f"🔥 Top Songs:\n{songs_list}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎤 /lyrics {info['top_songs'][0]} to see lyrics\n"
        f"📚 /wiki {info['name']} for full bio"
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
