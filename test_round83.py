"""Round-83 tests: seamless Wikipedia fallback for unknown artists.

Production case (2026-09-26): NL "ADELA" and "/artist adela" both failed
("couldn't find a song", "couldn't find info") while "/wiki adela"
returned the full Adéla (singer) article. Root cause: the curated
36-artist DB in artist_service has Tyla but not ADÉLA, and
_build_fallback_artist_profile only tried EXACT Wikipedia page titles —
"adela"/"Adela" land on the given-name page (no music words) and it gave
up, never trying Wikipedia *search* (which is what /wiki uses).

Fix:
 1. _build_fallback_artist_profile: when exact titles fail the music gate,
    fall back to Wikipedia search (lazy — exact-hit latency unchanged).
 2. New _send_fallback_artist_profile(update, query) helper; /artist uses
    it, so the "try /wiki" bounce is gone.
 3. NL fast path: in the strict no-candidates dead-end branch, route
    through the helper instead of the "couldn't find a song" message.

Q1 (mistyped song vs lesser-known artist): the song path always wins —
the fallback lives strictly behind "zero song candidates", and the
music-words gate means only confirmed musician pages fire.
Q2 (latency): the probe never runs on any successful path (asserted via
call counts below); exact Wikipedia hits never trigger the search.
"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handlers


class FakeChat:
    id = 999001
    def send_action(self, action=None): pass


class FakeMsg:
    def __init__(self, text=''):
        self.text = text; self.texts = []; self.chat = FakeChat()
        self.message_id = 1
    def reply_text(self, t, **kw):
        self.texts.append(str(t)); return self
    def edit_text(self, t, **kw):
        self.texts.append('EDIT:' + str(t)); return self


class FakeUser: id = 999001


class FakeUpdate:
    effective_user = FakeUser()
    def __init__(self, text=''):
        self.message = FakeMsg(text)
        self.effective_chat = FakeChat()
        self.effective_message = self.message


class FakeCtx:
    def __init__(self, args=None):
        self.args = args or []
        self.user_data = {}; self.chat_data = {}


passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _resp(status, payload):
    m = MagicMock(); m.status_code = status; m.json.return_value = payload
    return m


GIVEN_NAME = {'title': 'Adela', 'description': 'feminine given name',
              'extract': 'Adela is a feminine given name of Germanic origin.'}
SINGER_PAGE = {'title': 'Adéla (singer)', 'description': 'Slovak singer',
               'extract': 'Adéla Jergová (born 2003) is a Slovak singer.'}
MUSICIAN_EXACT = {'title': 'Some Musician', 'description': 'American singer',
                  'extract': 'Some Musician is an American singer.'}


def _req_get_adela(url, **kw):
    if url.endswith('/adela'):
        return _resp(404, {})
    if url.endswith('/Adela'):
        return _resp(200, GIVEN_NAME)
    if 'Ad%C3%A9la' in url or 'Adéla' in url:
        return _resp(200, SINGER_PAGE)
    return _resp(404, {})


# 1. adela: exact titles fail the music gate, search finds the singer page.
with patch('requests.get', side_effect=_req_get_adela), \
     patch('services.ai_info_service._search_wikipedia',
           return_value={'title': 'Adéla (singer)'}) as mock_search, \
     patch.object(handlers, '_fetch_artist_top_songs', return_value=[]):
    prof = handlers._build_fallback_artist_profile('adela')
check("adela resolves via wikipedia search",
      prof and prof['name'] == 'Adéla (singer)', str(prof)[:80])
check("adela card renders", prof and '🎤' in prof['text'], "")
check("search was actually consulted", mock_search.called, "")

# 2. Exact hit: search must NOT run (latency unchanged for existing hits).
with patch('requests.get', return_value=_resp(200, MUSICIAN_EXACT)), \
     patch('services.ai_info_service._search_wikipedia') as mock_search, \
     patch.object(handlers, '_fetch_artist_top_songs', return_value=[]):
    prof = handlers._build_fallback_artist_profile('some musician')
check("exact wikipedia hit still resolves", prof and prof['name'] == 'Some Musician', "")
check("exact hit never triggers search (no added latency)", not mock_search.called, "")

# 3. Non-musician: everything fails the gate -> None (honest miss).
with patch('requests.get', return_value=_resp(200, GIVEN_NAME)), \
     patch('services.ai_info_service._search_wikipedia', return_value=None), \
     patch.object(handlers, '_fetch_artist_top_songs', return_value=[]):
    prof = handlers._build_fallback_artist_profile('adela')
check("non-musician query still returns None", prof is None, str(prof)[:80])

# 4. /artist adela -> wikipedia card, no bounce message.
with patch.object(handlers, 'get_artist_info', return_value=None), \
     patch.object(handlers, '_build_fallback_artist_profile',
                  return_value={'name': 'Adéla', 'text': '🎤 Adéla\nbio',
                                'top_songs': []}):
    u = FakeUpdate(); ctx = FakeCtx(['adela'])
    handlers.artist_command(u, ctx)
    blob = '\n'.join(u.message.texts)
check("/artist adela sends wikipedia card",
      '🎤 Adéla' in blob and "couldn't find info" not in blob, blob[:100])

# 5. /artist total miss -> original not-found message verbatim.
with patch.object(handlers, 'get_artist_info', return_value=None), \
     patch.object(handlers, '_build_fallback_artist_profile', return_value=None):
    u = FakeUpdate(); ctx = FakeCtx(['zzzznomatch'])
    handlers.artist_command(u, ctx)
    blob = '\n'.join(u.message.texts)
check("/artist total miss keeps honest message",
      "couldn't find info" in blob and "/wiki zzzznomatch" in blob, blob[:100])

# 6. NL dead-end ("Adela", zero song candidates) -> artist card via fallback.
with patch('services.nlp_router.search_song_candidates', return_value=[]), \
     patch.object(handlers, '_build_fallback_artist_profile',
                  return_value={'name': 'Adéla', 'text': '🎤 Adéla\nbio',
                                'top_songs': []}):
    u = FakeUpdate('Adela')
    handlers.natural_language_handler(u, FakeCtx())
    blob = '\n'.join(u.message.texts)
check("NL dead-end resolves lesser-known artist",
      '🎤 Adéla' in blob and "couldn't find a song" not in blob, blob[:100])

# 7. NL dead-end with no wikipedia hit -> original message verbatim.
with patch('services.nlp_router.search_song_candidates', return_value=[]), \
     patch.object(handlers, '_build_fallback_artist_profile', return_value=None):
    u = FakeUpdate('Zzzznomatch')
    handlers.natural_language_handler(u, FakeCtx())
    blob = '\n'.join(u.message.texts)
check("NL true dead-end keeps original message",
      "couldn't find a song called" in blob and "Artist - Song" in blob, blob[:100])

# 8. Q1 guard: song candidates exist -> wikipedia NEVER consulted.
with patch('services.nlp_router.search_song_candidates',
           return_value=[{'artist': 'The Weeknd', 'song': 'Blinding Lights'}]), \
     patch('services.nlp_router.is_dominant_match', return_value=True), \
     patch.object(handlers, '_build_fallback_artist_profile') as mock_fb:
    u = FakeUpdate('Blinding Lights')
    handlers.natural_language_handler(u, FakeCtx())
    blob = '\n'.join(u.message.texts)
check("song interpretation wins: fallback not consulted",
      not mock_fb.called, "")
check("song confirmation path intact",
      "couldn't find a song" not in blob, blob[:100])

# 9. Q2 guard: curated artist (Tyla) never touches wikipedia fallback.
with patch.object(handlers, '_build_fallback_artist_profile') as mock_fb:
    u = FakeUpdate('Tyla')
    handlers.natural_language_handler(u, FakeCtx())
    blob = '\n'.join(u.message.texts)
check("curated artist path never touches wikipedia",
      not mock_fb.called and '🎤 Tyla' in blob, blob[:80])

# ── Round-83b: display_name vs lookup_name split ─────────────────────────
# Wikipedia disambiguation ("Adéla (singer)") stays on the card title and
# wiki URL, but Last.fm and YouTube use the stripped name. The "Pick a
# song" line only renders when songs exist.

with patch('requests.get', side_effect=_req_get_adela), \
     patch('services.ai_info_service._search_wikipedia',
           return_value={'title': 'Adéla (singer)'}), \
     patch.object(handlers, '_fetch_artist_top_songs',
                  return_value=[]) as mock_top:
    prof = handlers._build_fallback_artist_profile('adela')
check("83b: last.fm queried with stripped name",
      mock_top.called and mock_top.call_args[0][0] == 'Adéla',
      str(mock_top.call_args))
check("83b: youtube url uses stripped name",
      'search_query=Ad%C3%A9la+official' in prof['text']
      or 'search_query=Adéla+official' in prof['text'],
      prof['text'][-160:])
check("83b: youtube url has no (singer)",
      '(singer)' not in prof['text'].split('🎬')[1].split('\n')[0], "")
check("83b: wiki url keeps disambiguation",
      'Adéla_(singer)' in prof['text'] or 'Ad%C3%A9la_(singer)' in prof['text'], "")
check("83b: card title keeps disambiguation",
      prof['text'].startswith('🎤 Adéla (singer)'), prof['text'][:30])
check("83b: no songs -> no dangling pick-a-song line",
      'Pick a song below to explore' not in prof['text'], "")

with patch('requests.get', side_effect=_req_get_adela), \
     patch('services.ai_info_service._search_wikipedia',
           return_value={'title': 'Adéla (singer)'}), \
     patch.object(handlers, '_fetch_artist_top_songs',
                  return_value=['Nicole Kidman']):
    prof = handlers._build_fallback_artist_profile('adela')
check("83b: songs present -> pick-a-song line rendered",
      'Pick a song below to explore' in prof['text'], "")
check("83b: profile name stays the display name",
      prof['name'] == 'Adéla (singer)', prof['name'])

print(f"\nround83: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
