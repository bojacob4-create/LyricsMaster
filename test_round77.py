"""Round 77: Spotify artist-script bridge for non-Latin artist names.

Chart sources may list artists in their native script (Apple Music Korea
gives 아이유, not IU). The bridge asks Spotify's own artist index to map
the raw name to its Latin stage name before the normal search+score
pipeline runs. All network access is mocked.

Contract under test:
  1. Hangul artist bridges (아이유 -> IU) and the track then resolves.
  2. Bridge with zero hits -> original name kept, track unresolved, no crash.
  3. Bridge API error -> original name kept, save continues, miss NOT cached.
  4. Latin artists -> zero artist-search calls (today's path untouched).
  5. Same non-Latin artist twice -> one artist-search call (cache).
  6. Script detection: Hangul/CJK/Arabic/Cyrillic flagged; Latin with
     diacritics (Beyonce) NOT flagged.
"""
import sys
from unittest import mock

sys.path.insert(0, ".")

from services import spotify_auth as auth
from services import spotify_export as export

passed, failed = 0, 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


_UID = 169570389


def _track(name, artist, uri="spotify:track:xyz"):
    return {"name": name, "uri": uri,
            "artists": [{"name": artist}], "popularity": 80}


class _Api:
    """Mock for auth.api_get; routes on params['type'] and records calls."""

    def __init__(self, artist_hits=None, tracks=None, boom_artist=False):
        # artist_hits: raw query -> bridged Latin name (absent = no hits)
        self.artist_hits = artist_hits or {}
        self.tracks = tracks or []
        self.boom_artist = boom_artist
        self.artist_calls = []
        self.track_calls = []

    def __call__(self, path, user_id, params=None):
        params = params or {}
        if params.get("type") == "artist":
            q = params.get("q", "")
            self.artist_calls.append(q)
            if self.boom_artist:
                raise RuntimeError("artist search exploded")
            name = self.artist_hits.get(q)
            items = [{"name": name}] if name else []
            return {"artists": {"items": items}}
        q = (params.get("q", "") or "").lower()
        self.track_calls.append(params.get("q", ""))
        hits = [t for t in self.tracks if t["name"].lower() in q]
        return {"tracks": {"items": hits}}


def _run(api, tracks):
    export._artist_bridge_cache.clear()
    with mock.patch.object(export.auth, "api_get", api), \
         mock.patch.object(export.time, "sleep"):
        return export.resolve_tracks(tracks, _UID)


# 1. Bridge resolves ---------------------------------------------------------
api = _Api(artist_hits={"아이유": "IU"},
           tracks=[_track("Dear my crazy soulmate", "IU",
                         "spotify:track:iu123")])
uris, unresolved = _run(api, [("아이유", "Dear my crazy soulmate")])
check("bridge: Hangul artist resolves via bridged name",
      uris == ["spotify:track:iu123"] and unresolved == [])
check("bridge: artist search issued once", api.artist_calls == ["아이유"])

# 2. Zero hits -> original name, unresolved, no crash --------------------------
api = _Api(artist_hits={}, tracks=[])
uris, unresolved = _run(api, [("노스탈지아밴드", "노스탈지아")])
check("no hits: track unresolved, not crashed",
      uris == [] and unresolved == [{"artist": "노스탈지아밴드",
                                     "title": "노스탈지아"}])
# second resolve_tracks call with a FRESH mock (the shared one above
# already logged a lookup); the cache must suppress the second lookup.
api2 = _Api(artist_hits={}, tracks=[])
export._artist_bridge_cache.clear()
with mock.patch.object(export.auth, "api_get", api2), \
     mock.patch.object(export.time, "sleep"):
    export.resolve_tracks([("노스탈지아밴드", "노스탈지아"),
                           ("노스탈지아밴드", "다른노래")], _UID)
check("no hits: cached miss -> single artist lookup for 2 tracks",
      api2.artist_calls == ["노스탈지아밴드"])

# 3. Bridge error -> fallback, not cached --------------------------------------
api = _Api(artist_hits={"아이유": "IU"}, tracks=[], boom_artist=True)
uris, unresolved = _run(api, [("아이유", "노래1"), ("아이유", "노래2")])
check("bridge error: both tracks attempted with original name",
      len(uris) == 0 and len(unresolved) == 2)
check("bridge error: miss NOT cached (retried per track)",
      api.artist_calls == ["아이유", "아이유"])

# 4. Latin artists never trigger the bridge ------------------------------------
api = _Api(artist_hits={"Taylor Swift": "WRONG"},
           tracks=[_track("Lemonade", "aespa", "spotify:track:lm1")])
uris, unresolved = _run(api, [("aespa", "Lemonade"),
                              ("Beyoncé", "Halo")])
check("latin: no artist-search calls at all", api.artist_calls == [])
check("latin: normal matching unaffected",
      uris == ["spotify:track:lm1"])

# 5. Cache: same Hangul artist twice -> one lookup ------------------------------
api = _Api(artist_hits={"에이티즈": "ATEEZ"},
           tracks=[_track("BAD", "ATEEZ", "spotify:track:at1"),
                   _track("BOUNCY", "ATEEZ", "spotify:track:at2")])
uris, unresolved = _run(api, [("에이티즈", "BAD"), ("에이티즈", "BOUNCY")])
check("cache: one artist lookup for two tracks",
      api.artist_calls == ["에이티즈"])
check("cache: both tracks resolved via bridged name",
      uris == ["spotify:track:at1", "spotify:track:at2"])

# 6. Script detection -----------------------------------------------------------
cases = {
    "아이유": True,          # Hangul
    "ノスタルジア": True,    # Katakana
    "周杰伦": True,          # CJK
    "أم كلثوم": True,        # Arabic
    "Мумий Тролль": True,   # Cyrillic
    "IU": False,
    "Beyoncé": False,        # Latin-1 diacritic, not a script change
    "(G)I-DLE": False,
    "": False,
}
ok = all(export._has_non_latin_script(k) == v for k, v in cases.items())
check("script detection across scripts", ok)

print(f"\nround77: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
