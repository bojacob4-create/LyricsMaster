import logging
import requests
from collections import deque
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
    'tate mcrae': {'name': 'Tate McRae', 'genre': 'Pop / Dance-pop', 'debut': 2017, 'country': 'Canada',
                   'top_songs': ['greedy', "You Broke Me First", "She's All I Wanna Be", 'Exes', 'Sports car']},
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
    # Arabic artists (round 6 QA) — the user base is in Kuwait; Arabic names
    # must resolve to artist cards, not dead-end song lookups.
    'sherine': {'name': 'Sherine', 'genre': 'Arabic Pop', 'debut': 2000, 'country': 'Egypt',
                'top_songs': ['Ah Ya Leil', 'Mashaer', 'Kalam Eineh', 'Sabry Aalil', 'Ana Fel Gharam']},
    'amr diab': {'name': 'Amr Diab', 'genre': 'Arabic Pop', 'debut': 1983, 'country': 'Egypt',
                 'top_songs': ['Tamally Maak', 'Nour El Ain', 'Wayah', 'El Leila', 'Khalik Fekrni']},
    'elissa': {'name': 'Elissa', 'genre': 'Arabic Pop', 'debut': 1998, 'country': 'Lebanon',
               'top_songs': ['Aaks Elly Shayfak', 'Krahni', 'Betmoun', 'Ajmal Ehsas', 'Ya Merayti']},
    'nancy ajram': {'name': 'Nancy Ajram', 'genre': 'Arabic Pop', 'debut': 1998, 'country': 'Lebanon',
                    'top_songs': ['Inta Eyh', 'Ah W Noss', 'Ya Tabtab', 'Fi Hagat', 'Badna Nwalee El Jaw']},
    'fairuz': {'name': 'Fairuz', 'genre': 'Arabic Classic', 'debut': 1957, 'country': 'Lebanon',
               'top_songs': ['Nassam Alayna El Hawa', 'Aatini El Nay', 'Shady', 'Bhebbak Ya Loubnan', 'Kifak Inta']},
}

# Arabic-script aliases → the Latin DB keys above.
_ARABIC_ARTIST_ALIASES = {
    'شيرين': 'sherine',
    'شيرين عبد الوهاب': 'sherine',
    'عمرو دياب': 'amr diab',
    'اليسا': 'elissa',
    'إليسا': 'elissa',
    'نانسي عجرم': 'nancy ajram',
    'فيروز': 'fairuz',
}
ARTIST_DATABASE.update({alias: ARTIST_DATABASE[key]
                        for alias, key in _ARABIC_ARTIST_ALIASES.items()
                        if key in ARTIST_DATABASE})

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
    'soul': [
        {'artist': 'Adele', 'song': 'Rolling in the Deep', 'note': 'Soulful powerhouse vocal'},
        {'artist': 'Sam Cooke', 'song': 'A Change Is Gonna Come', 'note': 'Timeless soul classic'},
        {'artist': 'Aretha Franklin', 'song': 'Respect', 'note': 'Iconic soul anthem'},
        {'artist': 'Alicia Keys', 'song': 'If I Ain\'t Got You', 'note': 'Modern soul ballad'},
        {'artist': 'John Legend', 'song': 'All of Me', 'note': 'Soulful love song'},
        {'artist': 'Leon Bridges', 'song': 'Coming Home', 'note': 'Retro-soul revival'},
        {'artist': 'H.E.R.', 'song': 'Best Part', 'note': 'Contemporary neo-soul'},
        {'artist': 'Teddy Swims', 'song': 'Lose Control', 'note': 'Modern soul vocal power'},
        {'artist': 'Amy Winehouse', 'song': 'Back to Black', 'note': 'Soul-jazz masterpiece'},
        {'artist': 'Hozier', 'song': 'Take Me to Church', 'note': 'Soul-rock crossover'},
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
    'r&b': 'rnb', 'r and b': 'rnb',
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
    # ── Expansion: global, multi-genre, multi-era (120 total) ──
    {'artist': 'Ayra Starr', 'song': 'Rush'},
    {'artist': 'Wizkid', 'song': 'Essence'},
    {'artist': 'Davido', 'song': 'Fall'},
    {'artist': 'CKay', 'song': 'Love Nwantiti'},
    {'artist': 'Tems', 'song': 'Free Mind'},
    {'artist': 'Asake', 'song': 'Lonely At The Top'},
    {'artist': 'Omah Lay', 'song': 'Soso'},
    {'artist': 'Fireboy DML', 'song': 'Peru'},
    {'artist': 'Joeboy', 'song': 'Alcohol'},
    {'artist': 'King Promise', 'song': 'Terminator'},
    {'artist': 'Tate McRae', 'song': 'greedy'},
    {'artist': 'Gracie Abrams', 'song': "I Love You, I'm Sorry"},
    {'artist': 'Chappell Roan', 'song': 'Good Luck, Babe!'},
    {'artist': 'Charli XCX', 'song': '360'},
    {'artist': 'Billie Eilish', 'song': 'bad guy'},
    {'artist': 'Dua Lipa', 'song': 'Houdini'},
    {'artist': 'Ariana Grande', 'song': 'we can\'t be friends'},
    {'artist': 'Sabrina Carpenter', 'song': 'Please Please Please'},
    {'artist': 'Taylor Swift', 'song': 'Cruel Summer'},
    {'artist': 'Olivia Rodrigo', 'song': 'vampire'},
    {'artist': 'Drake', 'song': 'One Dance'},
    {'artist': 'Kendrick Lamar', 'song': 'Not Like Us'},
    {'artist': 'Travis Scott', 'song': 'Goosebumps'},
    {'artist': 'Doja Cat', 'song': 'Paint The Town Red'},
    {'artist': 'Nicki Minaj', 'song': 'Super Freaky Girl'},
    {'artist': 'Cardi B', 'song': 'I Like It'},
    {'artist': '21 Savage', 'song': 'a lot'},
    {'artist': 'Future', 'song': 'WAIT FOR U'},
    {'artist': 'J. Cole', 'song': 'No Role Modelz'},
    {'artist': 'SZA', 'song': 'Snooze'},
    {'artist': 'The Weeknd', 'song': 'Die For You'},
    {'artist': 'Frank Ocean', 'song': 'Pink + White'},
    {'artist': 'Daniel Caesar', 'song': 'Get You'},
    {'artist': 'H.E.R.', 'song': 'Damage'},
    {'artist': 'Summer Walker', 'song': 'Girls Need Love'},
    {'artist': 'Brent Faiyaz', 'song': 'Dead Man Walking'},
    {'artist': 'Steve Lacy', 'song': 'Bad Habit'},
    {'artist': 'Victoria Monét', 'song': 'On My Mama'},
    {'artist': 'Usher', 'song': "DJ Got Us Fallin' In Love"},
    {'artist': 'Bad Bunny', 'song': 'Tití Me Preguntó'},
    {'artist': 'Shakira', 'song': 'Bzrp Music Sessions, Vol. 53'},
    {'artist': 'Karol G', 'song': 'Provenza'},
    {'artist': 'Rauw Alejandro', 'song': 'Todo de Ti'},
    {'artist': 'Rosalía', 'song': 'Despechá'},
    {'artist': 'Peso Pluma', 'song': 'Ella Baila Sola'},
    {'artist': 'J Balvin', 'song': 'Mi Gente'},
    {'artist': 'Maluma', 'song': 'Hawái'},
    {'artist': 'Queen', 'song': "Don't Stop Me Now"},
    {'artist': 'The Beatles', 'song': 'Here Comes The Sun'},
    {'artist': 'Arctic Monkeys', 'song': '505'},
    {'artist': 'Tame Impala', 'song': 'The Less I Know The Better'},
    {'artist': 'Red Hot Chili Peppers', 'song': 'Californication'},
    {'artist': 'Oasis', 'song': 'Wonderwall'},
    {'artist': 'The Strokes', 'song': 'Last Nite'},
    {'artist': 'Foo Fighters', 'song': 'Everlong'},
    {'artist': 'Linkin Park', 'song': 'In The End'},
    {'artist': 'Hozier', 'song': 'Too Sweet'},
    {'artist': 'Bon Iver', 'song': 'Skinny Love'},
    {'artist': 'Vampire Weekend', 'song': 'A-Punk'},
    {'artist': 'Glass Animals', 'song': 'Heat Waves'},
    {'artist': 'Clairo', 'song': 'Bags'},
    {'artist': 'Phoebe Bridgers', 'song': 'Motion Sickness'},
    {'artist': 'The 1975', 'song': 'Somebody Else'},
    {'artist': 'Fred again..', 'song': 'places to be'},
    {'artist': 'Disclosure', 'song': 'You & Me'},
    {'artist': 'Calvin Harris', 'song': 'Summer'},
    {'artist': 'David Guetta', 'song': 'Titanium'},
    {'artist': 'Swedish House Mafia', 'song': "Don't You Worry Child"},
    {'artist': 'Flume', 'song': 'Never Be Like You'},
    {'artist': 'Kaytranada', 'song': '10%'},
    {'artist': 'Jung Kook', 'song': 'Seven'},
    {'artist': 'BTS', 'song': 'Dynamite'},
    {'artist': 'BLACKPINK', 'song': 'How You Like That'},
    {'artist': 'NewJeans', 'song': 'Super Shy'},
    {'artist': 'Stray Kids', 'song': 'S-Class'},
    {'artist': 'Michael Jackson', 'song': 'Billie Jean'},
    {'artist': 'Whitney Houston', 'song': 'I Wanna Dance with Somebody'},
    {'artist': 'ABBA', 'song': 'Dancing Queen'},
    {'artist': 'Elton John', 'song': 'Cold Heart'},
    {'artist': 'Bee Gees', 'song': "Stayin' Alive"},
    {'artist': 'Toto', 'song': 'Africa'},
    {'artist': 'a-ha', 'song': 'Take On Me'},
    {'artist': 'Chris Stapleton', 'song': 'White Horse'},
    {'artist': 'Zach Bryan', 'song': 'Something in the Orange'},
    {'artist': 'Noah Kahan', 'song': 'Stick Season'},
    {'artist': 'Kacey Musgraves', 'song': 'Deeper Well'},
    {'artist': 'Rihanna', 'song': 'Umbrella'},
    {'artist': 'Rihanna', 'song': 'Diamonds'},
    {'artist': 'Adele', 'song': 'Rolling in the Deep'},
    {'artist': 'Sam Smith', 'song': 'Unholy'},
    {'artist': 'Doja Cat', 'song': 'Woman'},
    {'artist': 'Lizzo', 'song': 'About Damn Time'},
    {'artist': 'Jack Harlow', 'song': 'First Class'},
    {'artist': 'Metro Boomin', 'song': 'Creepin\''},
]


def _note_random_pick(user_id, pick):
    """Remember a random pick per user so /random avoids recent repeats."""
    if user_id is None:
        return
    dq = _recent_random_picks.get(user_id)
    if dq is None:
        dq = _recent_random_picks[user_id] = deque(maxlen=12)
    dq.append(f"{pick['artist']} - {pick['song']}".lower())


_recent_random_picks = {}


def resolve_genre_key(genre_query: str) -> Optional[str]:
    """Resolve a user's genre input (incl. aliases) to a canonical key,
    or None when it isn't a known genre."""
    genre_lower = (genre_query or '').lower().strip()
    resolved = GENRE_ALIASES.get(genre_lower, genre_lower)
    return resolved if resolved in GENRE_TOP_SONGS else None


def get_top_by_genre(genre_query: str) -> Optional[tuple]:
    """Top songs for a genre — 100% live (Apple home chart + Last.fm).

    Returns (genre, songs) or None when the genre is unknown OR every live
    source failed. The static GENRE_TOP_SONGS pool is intentionally NOT
    served here (it still backs quizzes etc.); callers show an honest
    charts-unreachable message instead of stale picks.
    """
    resolved = resolve_genre_key(genre_query)
    if not resolved:
        return None

    live = _get_live_genre_songs(resolved)
    if live:
        return resolved, live
    return None


def _dominant_note(songs: List[Dict]) -> str:
    """Most common per-song note; ties break by first appearance.

    A song's ↳ note is only worth rendering when it differs from this —
    the same note repeated under every song is noise (the Sources header
    already states it once). Missing/blank notes count as ''.
    """
    counts: Dict[str, int] = {}
    order: List[str] = []
    for s in songs or []:
        n = (s.get('note') or '').strip()
        if n not in counts:
            counts[n] = 0
            order.append(n)
        counts[n] += 1
    best, best_n = '', -1
    for n in order:
        if counts[n] > best_n:
            best, best_n = n, counts[n]
    return best


def format_top_songs(genre: str, songs: List[Dict]) -> str:
    genre_emojis = {
        'afrobeats': '🌍', 'pop': '🎤', 'rap': '🎙️', 'rnb': '💜',
        'rock': '🎸', 'latin': '💃', 'country': '🤠', 'kpop': '🇰🇷',
        'soul': '🎷',
    }
    emoji = genre_emojis.get(genre, '🎵')
    display_genre = genre.upper() if genre in ('rnb', 'kpop') else genre.title()

    lines = []
    rank_emojis = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
    common = _dominant_note(songs)
    for i, song in enumerate(songs):
        rank = rank_emojis[i] if i < len(rank_emojis) else '🎵'
        note = (song.get('note') or '').strip()
        if note and note != common:
            lines.append(f"{rank} {song['artist']} — {song['song']}\n   ↳ {note}")
        else:
            lines.append(f"{rank} {song['artist']} — {song['song']}")

    body = '\n\n'.join(lines)

    has_apple = any('Apple Music' in s.get('note', '') for s in songs)
    has_lastfm = any('Last.fm' in s.get('note', '') for s in songs)
    if has_apple and has_lastfm:
        source_line = "Sources: Apple Music Charts + Last.fm\n"
    elif has_lastfm:
        source_line = "Source: Last.fm\n"
    elif has_apple:
        source_line = "Source: Apple Music Charts\n"
    else:
        source_line = ""

    return (
        f"{emoji} Top {display_genre}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"{source_line}\n"
        f"{body}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎵 Pick a song below to explore:"
    )


def get_available_genres() -> List[str]:
    genres = list(GENRE_TOP_SONGS.keys())
    return genres


def get_random_song(user_id=None, genre=None) -> Optional[Dict]:
    """Pick a random song from LIVE charts — no static pools.

    - genre: pick from the live genre chart (Apple genre slice of the
      Top 100); falls back to the global chart when the genre slice is thin.
    - Otherwise: pick from the live Apple Music Top 100 (cached ~6h).
    - Fresh-release preference: songs released within the last 24 months are
      preferred (the charts are most-played, so viral oldies appear too);
      falls back to the full chart when too few fresh songs qualify.
    - Per-user recent picks are avoided (last 12) so /random feels fresh.
    - Returns None when the live chart is unreachable AND no cache exists;
      callers must degrade gracefully (friendly message, not a crash).
    """
    import random as rng
    from services.live_charts import (
        get_top_songs, get_top_by_genre, get_fresh_songs,
        search_songs_by_genre)

    recent = _recent_random_picks.get(user_id) if user_id else None

    pool: List[Dict] = []
    genre_missed: Optional[str] = None
    if genre:
        resolved = GENRE_ALIASES.get(genre.lower().strip(),
                                     genre.lower().strip())
        pool = get_fresh_songs(genre=resolved)
        if not pool:
            pool = get_top_by_genre(resolved)
        if not pool:
            # General fallback: live iTunes search for the genre itself.
            # Covers every genre iTunes knows (afrobeats, amapiano,
            # dancehall, jazz, …) — no per-genre special-casing needed.
            pool = search_songs_by_genre(resolved)
            if pool:
                logger.info(
                    f"/random: genre '{resolved}' via iTunes search "
                    f"({len(pool)} songs)")
        if not pool:
            # Nothing live for this genre anywhere: remember it so the
            # caller can be honest about the fallback instead of silently
            # serving an unrelated global-chart pick.
            genre_missed = resolved
            logger.info(
                f"/random: no live genre pool for '{resolved}', "
                "using global chart")

    if not pool:
        pool = get_fresh_songs()
        if pool:
            logger.info(f"/random: using fresh-release pool ({len(pool)} songs)")

    if not pool:
        pool = get_top_songs()

    if not pool:
        logger.warning("get_random_song: live chart unavailable, no cache")
        return None

    def _fresh(p):
        return (not recent
                or f"{p['artist']} - {p['song']}".lower() not in recent)

    pick = rng.choice(pool)
    for _ in range(15):
        if _fresh(pick):
            break
        pick = rng.choice(pool)

    pick = {'artist': pick['artist'], 'song': pick['song']}
    _note_random_pick(user_id, pick)
    if genre_missed:
        pick['genre_fallback'] = genre_missed
    return pick


def get_artist_info(name: str) -> Optional[Dict]:
    name_lower = name.lower().strip()

    if name_lower in ARTIST_DATABASE:
        return ARTIST_DATABASE[name_lower]

    for key, data in ARTIST_DATABASE.items():
        if name_lower in key or key in name_lower:
            return data

    for key, data in ARTIST_DATABASE.items():
        key_words = set(key.split())
        significant_parts = [p for p in name_lower.split() if len(p) > 2]
        if significant_parts and all(p in key_words for p in significant_parts):
            return data

    return None


def format_artist_info(info: Dict) -> str:
    name_slug = info['name'].replace(' ', '+')
    wiki_url = f"https://en.wikipedia.org/wiki/{info['name'].replace(' ', '_')}"
    yt_url = f"https://www.youtube.com/results?search_query={name_slug}+official"

    return (
        f"🎤 {info['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎵 Genre: {info['genre']}\n"
        f"📅 Debut: {info['debut']}\n"
        f"🌍 From: {info['country']}\n\n"
        f"🔗 Links:\n"
        f"  📚 {wiki_url}\n"
        f"  🎬 {yt_url}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 Pick a song below to explore:"
    )


# Per-country Apple chart cache: country code -> {'raw', 'trending', 'timestamp'}.
# Each genre pulls its home chart (kpop -> Korea, afrobeats -> Nigeria, the
# rest -> US) so every genre has a genuine "charting now" source.
_chart_cache = {}
CHART_CACHE_TTL = 3600

# genre key -> (apple chart country, apple genre tag(s)).
APPLE_GENRE_MAP = {
    'pop': ('us', 'Pop'),
    'rap': ('us', 'Hip-Hop/Rap'),
    'rnb': ('us', 'R&B/Soul'),
    'rock': ('us', ['Rock', 'Alternative']),
    'country': ('us', 'Country'),
    'latin': ('us', 'Latin'),
    'kpop': ('kr', 'K-Pop'),
    'soul': ('us', 'R&B/Soul'),
    'afrobeats': ('ng', 'Afrobeats'),
}

# genre key -> Apple RSS genre id for the genre's OWN chart
# (https://itunes.apple.com/us/rss/topsongs/.../genre=<id>/json).
# Keys absent here (kpop, afrobeats) have no RSS genre chart and keep the
# country-chart tag-filter path.
APPLE_RSS_GENRE_ID = {
    'pop': '14',
    'rap': '18',
    'rnb': '15',
    'soul': '15',
    'rock': '21',
    'country': '6',
    'latin': '12',
}


def _fetch_apple_genre_chart(genre_id: str, country: str = 'us',
                             limit: int = 100) -> Optional[List[Dict]]:
    """Fetch a genre's own Apple chart (e.g. the Pop Top 100)."""
    try:
        r = session.get(
            f'https://itunes.apple.com/{country}/rss/topsongs/'
            f'limit={limit}/genre={genre_id}/json',
            timeout=10,
            headers={'User-Agent': 'LyricsMasterBot/1.0'})
        if r.status_code != 200:
            return None
        entries = r.json().get('feed', {}).get('entry', [])
        songs = []
        for e in entries:
            artist = ((e.get('im:artist') or {}).get('label') or '').strip()
            name = ((e.get('im:name') or {}).get('label') or '').strip()
            if not artist or not name:
                continue
            songs.append({'artist': artist, 'song': name, 'genres': []})
        return songs if len(songs) >= 10 else None
    except Exception as e:
        logger.debug(f"Apple genre chart fetch error ({genre_id}): {e}")
        return None


_genre_chart_cache: Dict[tuple, dict] = {}


def _get_cached_genre_chart(genre_id: str,
                            country: str = 'us') -> Optional[List[Dict]]:
    """Hourly-cached genre chart. []/None on any miss. Never raises."""
    import time
    now = time.time()
    key = (country, genre_id)
    entry = _genre_chart_cache.get(key)
    if entry and entry['songs'] and \
            (now - entry['timestamp']) < CHART_CACHE_TTL:
        return entry['songs']
    songs = _fetch_apple_genre_chart(genre_id, country)
    if not songs:
        songs = _fetch_apple_genre_chart(genre_id, country)  # one retry
    if songs:
        _genre_chart_cache[key] = {'songs': songs, 'timestamp': now}
    return songs


# genre key -> Last.fm tag. Fills thin Apple slices so a /top card is always
# full AND always live — the static curated pool is never served here.
LASTFM_GENRE_TAG = {
    'pop': 'pop',
    'rap': 'hip-hop',
    'rnb': 'rnb',
    'rock': 'rock',
    'latin': 'latin',
    'country': 'country',
    'kpop': 'k-pop',
    'soul': 'soul',
    'afrobeats': 'afrobeats',
}
_genre_tag_cache = {}
GENRE_TAG_TTL = 6 * 3600


def _fetch_apple_chart(country: str = 'us') -> Optional[List[Dict]]:
    """Fetch Apple's most-played Top 100 for a country ('us', 'kr', 'ng'...)."""
    try:
        r = session.get(
            f'https://rss.applemarketingtools.com/api/v2/{country}/music/most-played/100/songs.json',
            timeout=10
        )
        if r.status_code != 200:
            return None

        results = r.json().get('feed', {}).get('results', [])
        if not results:
            return None

        songs = []
        for item in results:
            artist = item.get('artistName', '').strip()
            name = item.get('name', '').strip()
            if not artist or not name:
                continue
            genres = [g.get('name', '') for g in item.get('genres', []) if g.get('name') != 'Music']
            songs.append({'artist': artist, 'song': name, 'genres': genres})

        return songs if len(songs) >= 10 else None

    except Exception as e:
        logger.debug(f"Apple chart fetch error: {e}")
        return None


def _get_cached_chart(country: str = 'us') -> Optional[List[Dict]]:
    import time
    now = time.time()
    entry = _chart_cache.get(country)
    if entry and entry['raw'] and (now - entry['timestamp']) < CHART_CACHE_TTL:
        return entry['raw']

    raw = _fetch_apple_chart(country)
    if not raw:
        # One retry: the Apple RSS endpoint occasionally drops a single
        # request — don't give up on a lone blip.
        raw = _fetch_apple_chart(country)
    if raw:
        new_entry = {'raw': raw, 'trending': None, 'timestamp': now}
        trending = []
        seen_artists = set()
        for s in raw:
            if s['artist'].lower() not in seen_artists:
                seen_artists.add(s['artist'].lower())
                trending.append({'artist': s['artist'], 'song': s['song']})
                if len(trending) >= 10:
                    break
        new_entry['trending'] = trending
        _chart_cache[country] = new_entry
    return raw


def get_trending_songs() -> tuple:
    raw = _get_cached_chart()
    trending = _chart_cache.get('us', {}).get('trending')
    if raw and trending:
        return trending, True

    import random
    pool = list(TRENDING_SONGS)
    random.shuffle(pool)
    return pool[:8], False


def get_us_chart_deep() -> List[Dict]:
    """Full US Apple chart, deduped by artist (~90 songs).

    Same source as the 10-song trending slice above, just deep — gives
    /newmusic's bare path the same rotation room the genre slices got in
    round 52.  Does NOT change get_trending_songs()' contract (used by
    /trending).  [] when the chart fetch fails.  Never raises.
    """
    try:
        raw = _get_cached_chart('us')
    except Exception:
        raw = None
    out, seen = [], set()
    for s in raw or []:
        try:
            key = str(s.get('artist', '')).lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append({'artist': s.get('artist', ''),
                            'song': s.get('song', '')})
        except Exception:
            continue
    return out


def _fetch_lastfm_tag_tracks(tag: str, limit: int = 25) -> List[Dict]:
    """Last.fm tag.getTopTracks — what the world's listeners are playing now.

    Same proven pattern as the /mood live tier. [] on any miss. Never raises.
    """
    import os as _os
    try:
        import requests as _requests
    except Exception:
        return []
    api_key = _os.environ.get('LASTFM_API_KEY', '')
    if not api_key:
        return []
    try:
        r = _requests.get(
            'https://ws.audioscrobbler.com/2.0/',
            params={'method': 'tag.gettoptracks', 'tag': tag,
                    'api_key': api_key, 'format': 'json', 'limit': limit},
            timeout=8,
            headers={'User-Agent': 'LyricsMasterBot/1.0'})
        tracks = ((r.json() or {}).get('tracks') or {}).get('track') or []
        out, seen = [], set()
        for t in tracks:
            if not isinstance(t, dict):
                continue
            a = str((t.get('artist') or {}).get('name') or '').strip()
            name = str(t.get('name') or '').strip()
            if not a or not name or len(name) > 60:
                continue
            k = (a.lower(), name.lower())
            if k in seen:
                continue
            seen.add(k)
            out.append({'artist': a, 'song': name})
        return out
    except Exception as e:
        logger.debug(f"Last.fm tag tracks error for '{tag}': {e}")
        return []


def _get_lastfm_genre_songs(genre_key: str, exclude_artists=frozenset(),
                            exclude_songs=frozenset(),
                            limit: int = 7) -> List[Dict]:
    """Fill a thin Apple genre slice with live Last.fm tag tracks.

    6h cache per tag. Dedupes against the Apple picks. Every song carries
    note 'Popular on Last.fm'. [] when Last.fm is down/keyless. Never raises.
    """
    import time as _time
    tag = LASTFM_GENRE_TAG.get(genre_key)
    if not tag or limit <= 0:
        return []
    now = _time.time()
    entry = _genre_tag_cache.get(tag)
    if entry and (now - entry[0]) < GENRE_TAG_TTL:
        tracks = entry[1]
    else:
        tracks = _fetch_lastfm_tag_tracks(tag)
        _genre_tag_cache[tag] = (now, tracks)
        while len(_genre_tag_cache) > 12:
            _genre_tag_cache.pop(next(iter(_genre_tag_cache)))
    out, seen_a, seen_s = [], set(exclude_artists), set(exclude_songs)
    for t in tracks:
        akey = t['artist'].lower()
        skey = (akey, t['song'].lower())
        if akey in seen_a or skey in seen_s:
            continue
        seen_a.add(akey)
        seen_s.add(skey)
        out.append({'artist': t['artist'], 'song': t['song'],
                    'note': 'Popular on Last.fm'})
        if len(out) >= limit:
            break
    return out


def _get_live_genre_songs(genre_key: str,
                          deep: bool = False) -> Optional[List[Dict]]:
    """All-live genre top list.

    Tier 1: the genre's Apple chart — with deep=True the genre's OWN chart
    (pop -> the Pop Top 100 via APPLE_RSS_GENRE_ID; keys without an RSS
    genre, e.g. kpop/afrobeats, keep the home-country chart slice:
    kpop -> Korea, afrobeats -> Nigeria, rest -> US), artists deduped.
    With deep=False (the /top path) the home-country slice, as before.
    Tier 2: Last.fm tag tracks top the card up when the slice is thin.
    Returns None when EVERY live source fails — callers show an honest
    charts-unreachable message; the static pool is never served here.
    """
    mapping = APPLE_GENRE_MAP.get(genre_key)
    if not mapping:
        return None
    country, tags = mapping
    if isinstance(tags, str):
        tags = [tags]
    # /top (deep=False) keeps its exact round-51 contract: walk to 12,
    # Last.fm top-up only when the slice is thinner than 7.
    walk_to, min_full = (30, 30) if deep else (12, 7)

    songs = []
    seen_artists = set()
    seen_songs = set()
    gid = APPLE_RSS_GENRE_ID.get(genre_key) if deep else None
    raw = (_get_cached_genre_chart(gid, country) if gid
           else _get_cached_chart(country))
    if raw:
        for item in raw:
            if gid is None and not any(t in item.get('genres', [])
                                       for t in tags):
                continue
            akey = item['artist'].lower()
            skey = (akey, item['song'].lower())
            if akey in seen_artists or skey in seen_songs:
                continue
            seen_artists.add(akey)
            seen_songs.add(skey)
            songs.append({
                'artist': item['artist'],
                'song': item['song'],
                'note': 'Charting now on Apple Music',
            })
            if len(songs) >= walk_to:
                break

    if len(songs) < min_full:
        songs.extend(_get_lastfm_genre_songs(
            genre_key, exclude_artists=seen_artists,
            exclude_songs=seen_songs, limit=walk_to - len(songs)))

    return songs if songs else None


def format_trending(songs: List[Dict], is_live: bool = True) -> str:
    lines = []
    rank_emojis = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    common = _dominant_note(songs)
    for i, song in enumerate(songs):
        rank = rank_emojis[i] if i < len(rank_emojis) else '🎵'
        note = (song.get('note') or '').strip()
        if note and note != common:
            lines.append(f"{rank} {song['artist']} — {song['song']}\n   ↳ {note}")
        else:
            lines.append(f"{rank} {song['artist']} — {song['song']}")

    body = '\n\n'.join(lines)

    if is_live:
        header = "📈 Trending Now\n"
        sub = "Source: Apple Music Charts\n"
    else:
        header = "🌍 Popular Songs\n"
        sub = ""

    return (
        f"{header}"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"{sub}\n"
        f"{body}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎵 Pick a song below to explore:"
    )
