"""Round 73 — Spotify export for /mood and /top.

Covers services/spotify_auth.py (OAuth PKCE + token lifecycle) and
services/spotify_export.py (track matching + playlist ops) with a fully
mocked HTTP layer: ZERO real network calls.

Production paths are never touched: _TOKENS_PATH / _PENDING_PATH are
redirected to temp files per the round-70 lesson.

Run: python test_round73.py
"""

import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


def fresh_env():
    """Isolate auth module state: temp paths + clean pendings + test creds."""
    tmp = tempfile.mkdtemp(prefix="sp73_")
    auth._TOKENS_PATH = os.path.join(tmp, ".spotify_tokens.json")
    auth._PENDING_PATH = os.path.join(tmp, ".spotify_pending.json")
    auth._pending_links.clear()
    return tmp


def with_creds(fn):
    def wrapper():
        with mock.patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "cid123",
                                           "SPOTIFY_CLIENT_SECRET": "csec456"}):
            auth._collect_secrets_cache_reset()
            return fn()
    return wrapper


# The log-redaction module caches env secrets; our temp creds must not leak
# into other tests via that cache. (No-op if the hook is absent.)
def _reset_secret_cache():
    try:
        import log_redaction
        log_redaction._secrets_cache = None
    except Exception:
        pass


auth._collect_secrets_cache_reset = _reset_secret_cache


def mock_resp(status=200, body=None, headers=None):
    m = mock.Mock()
    m.status_code = status
    m.headers = headers or {}
    m.content = b"x" if body is not None else b""
    m.json = mock.Mock(return_value=body if body is not None else {})
    return m


def token_body(**kw):
    b = {"access_token": "acc_tok", "refresh_token": "ref_tok",
         "expires_in": 3600, "scope": "playlist-modify-private"}
    b.update(kw)
    return b


# ── 1. PKCE math ─────────────────────────────────────────────────────────────
v, c = auth.pkce_pair()
expect = base64.urlsafe_b64encode(
    hashlib.sha256(v.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
check("pkce challenge == S256(verifier)", c == expect)
check("pkce verifier urlsafe charset",
      all(ch.isalnum() or ch in "-_" for ch in v) and len(v) >= 43)
v2, _ = auth.pkce_pair()
check("pkce verifier random", v != v2)

# ── 2. authorize URL ─────────────────────────────────────────────────────────
fresh_env()


@with_creds
def _t_auth_url():
    url, state = auth.build_authorize_url(4242)
    check("auth url host", url.startswith(
        "https://accounts.spotify.com/authorize?"))
    check("auth url client_id", "client_id=cid123" in url)
    check("auth url redirect exact",
          "redirect_uri=http%3A%2F%2F127.0.0.1%3A8888%2Fcallback" in url)
    check("auth url scope", "scope=playlist-modify-private" in url)
    check("auth url S256", "code_challenge_method=S256" in url
          and "code_challenge=" in url)
    check("auth url state binds user", state.startswith("4242:"))
    pend = auth.get_pending_link(4242)
    check("pending link stored with verifier",
          bool(pend and pend.get("verifier") and pend["state"] == state))
    check("verifier NOT in url", pend["verifier"] not in url)
    # Second tap overwrites the pending flow (latest wins).
    url2, state2 = auth.build_authorize_url(4242)
    check("re-link overwrites pending",
          auth.get_pending_link(4242)["state"] == state2
          and state2 != state)


_t_auth_url()

# Not configured -> clean error, no URL.
fresh_env()
try:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SPOTIFY_CLIENT_ID", None)
        os.environ.pop("SPOTIFY_CLIENT_SECRET", None)
        auth.build_authorize_url(1)
    check("auth url requires config", False)
except auth.SpotifyNotConfigured:
    check("auth url requires config", True)

# ── 3. exchange_code ─────────────────────────────────────────────────────────
fresh_env()


@with_creds
def _t_exchange_ok():
    auth.build_authorize_url(77)
    with mock.patch.object(auth.requests, "post") as mp, \
         mock.patch.object(auth.requests, "get") as mg:
        mp.return_value = mock_resp(200, token_body())
        mg.return_value = mock_resp(200, {"id": "sp_user_1",
                                          "display_name": "Mo"})
        info = auth.exchange_code("AQDcode123", 77)
    check("exchange returns identity", info["display_name"] == "Mo")
    tok = auth.get_stored(77)
    check("exchange stores token pair",
          tok["access_token"] == "acc_tok"
          and tok["refresh_token"] == "ref_tok")
    check("exchange stores expiry in future", tok["expires_at"] > time.time())
    check("exchange drops pending", auth.get_pending_link(77) is None)
    # /me failure is non-fatal.
    auth.build_authorize_url(78)
    with mock.patch.object(auth.requests, "post") as mp, \
         mock.patch.object(auth.requests, "get") as mg:
        mp.return_value = mock_resp(200, token_body())
        mg.side_effect = Exception("down")
        info = auth.exchange_code("AQDcode9", 78)
    check("exchange survives /me failure",
          info["display_name"] is None and auth.is_linked(78))


_t_exchange_ok()


@with_creds
def _t_exchange_bad():
    # No pending flow at all.
    try:
        with mock.patch.object(auth.requests, "post") as mp:
            mp.return_value = mock_resp(200, token_body())
            auth.exchange_code("AQDwhatever", 999)
        check("exchange rejects missing pending", False)
    except auth.SpotifyLinkError:
        check("exchange rejects missing pending", True)
    # Expired pending.
    auth.build_authorize_url(100)
    auth._pending_links["100"]["created_at"] = time.time() - 3600
    try:
        with mock.patch.object(auth.requests, "post") as mp:
            mp.return_value = mock_resp(200, token_body())
            auth.exchange_code("AQDwhatever", 100)
        check("exchange rejects expired pending", False)
    except auth.SpotifyLinkError:
        check("exchange rejects expired pending", True)
    # Bad code: token endpoint 400 -> error, pending KEPT for retry.
    auth.build_authorize_url(101)
    with mock.patch.object(auth.requests, "post") as mp:
        mp.return_value = mock_resp(400, {"error": "invalid_grant"})
        try:
            auth.exchange_code("AQDbad", 101)
            check("exchange rejects bad code", False)
        except auth.SpotifyLinkError:
            check("exchange rejects bad code", True)
    check("bad code keeps pending for retry",
          auth.get_pending_link(101) is not None)


_t_exchange_bad()

# ── 4. ensure_access_token ───────────────────────────────────────────────────
fresh_env()


@with_creds
def _t_ensure():
    # Fresh token -> no HTTP at all.
    auth._store(5, "fresh_acc", "fresh_ref", 3600, auth.SCOPE)
    with mock.patch.object(auth.requests, "post") as mp:
        tok = auth.ensure_access_token(5)
    check("fresh token returned as-is", tok == "fresh_acc")
    check("fresh token makes no HTTP", mp.call_count == 0)
    # Expired token -> refresh grant, persisted.
    auth._store(6, "old_acc", "old_ref", -10, auth.SCOPE)
    with mock.patch.object(auth.requests, "post") as mp:
        mp.return_value = mock_resp(200, token_body(
            access_token="new_acc", refresh_token="new_ref"))
        tok = auth.ensure_access_token(6)
    check("expired token refreshed", tok == "new_acc")
    check("refresh grant used",
          mp.call_args[1]["data"]["grant_type"] == "refresh_token")
    stored = auth.get_stored(6)
    check("refreshed tokens persisted",
          stored["access_token"] == "new_acc"
          and stored["refresh_token"] == "new_ref"
          and stored["expires_at"] > time.time())
    # Refresh without rotation keeps the old refresh token.
    auth._store(7, "old_acc", "keep_ref", -10, auth.SCOPE)
    with mock.patch.object(auth.requests, "post") as mp:
        body = token_body(access_token="new_acc2")
        del body["refresh_token"]
        mp.return_value = mock_resp(200, body)
        auth.ensure_access_token(7)
    check("unrotated refresh token kept",
          auth.get_stored(7)["refresh_token"] == "keep_ref")
    # Never linked -> SpotifyUnlinked, no HTTP.
    with mock.patch.object(auth.requests, "post") as mp:
        try:
            auth.ensure_access_token(404)
            check("unlinked raises SpotifyUnlinked", False)
        except auth.SpotifyUnlinked:
            check("unlinked raises SpotifyUnlinked", True)
    check("unlinked makes no HTTP", mp.call_count == 0)


_t_ensure()

# ── 5. 401 -> one refresh + retry; double 401 -> unlink ─────────────────────
fresh_env()


@with_creds
def _t_401():
    auth._store(11, "stale_acc", "ref_11", 3600, auth.SCOPE)
    calls = {"n": 0}

    def fake_request(method, url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return mock_resp(401, {"error": {"status": 401}})
        return mock_resp(200, {"ok": True})

    with mock.patch.object(auth.requests, "request",
                           side_effect=fake_request), \
         mock.patch.object(auth.requests, "post") as mp:
        mp.return_value = mock_resp(200, token_body(access_token="acc2"))
        out = auth.api_get("/me", 11)
    check("401 retried once after refresh", out == {"ok": True}
          and calls["n"] == 2)
    check("retry used refreshed token",
          auth.get_stored(11)["access_token"] == "acc2")

    # 401 again after refresh -> unlink + SpotifyUnlinked.
    auth._store(12, "bad_acc", "bad_ref", 3600, auth.SCOPE)
    with mock.patch.object(auth.requests, "request",
                           return_value=mock_resp(401, {})), \
         mock.patch.object(auth.requests, "post") as mp:
        mp.return_value = mock_resp(200, token_body(access_token="acc3"))
        try:
            auth.api_get("/me", 12)
            check("double 401 raises SpotifyUnlinked", False)
        except auth.SpotifyUnlinked:
            check("double 401 raises SpotifyUnlinked", True)
    check("double 401 clears tokens", auth.get_stored(12) is None)


_t_401()

# ── 6. revoked refresh token -> unlink ───────────────────────────────────────
fresh_env()


@with_creds
def _t_revoked():
    auth._store(13, "old", "revoked_ref", -10, auth.SCOPE)
    with mock.patch.object(auth.requests, "post") as mp:
        mp.return_value = mock_resp(400, {"error": "invalid_grant"})
        try:
            auth.ensure_access_token(13)
            check("invalid_grant raises SpotifyUnlinked", False)
        except auth.SpotifyUnlinked:
            check("invalid_grant raises SpotifyUnlinked", True)
    check("invalid_grant clears tokens", auth.get_stored(13) is None)


_t_revoked()

# ── 7. scoring fixtures ──────────────────────────────────────────────────────
def cand(name, artist="The Weeknd", pop=80):
    return {"name": name, "uri": f"spotify:track:{name[:4]}",
            "artists": [{"name": artist}], "popularity": pop}


s_orig, _ = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights", pop=95))
s_live, f_live = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights - Live at SoFi Stadium", pop=60))
s_kar, f_kar = export.score_candidate(
    "The Weeknd", "Blinding Lights", cand("Blinding Lights (Karaoke)", pop=40))
s_trib, _ = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights - Tribute to The Weeknd", artist="Tribute Band",
         pop=30))
s_cover, _ = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights (Cover)", artist="Jane Doe", pop=70))
check("original scores highest",
      s_orig > s_live and s_orig > s_kar and s_orig > s_trib
      and s_orig > s_cover)
check("original above accept threshold", s_orig >= 70)
check("karaoke flagged", "karaoke" in f_kar)
check("live flagged", "live" in f_live)
check("karaoke below threshold", s_kar < 70)

s_rem, f_rem = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights (Remastered)", pop=90))
check("remastered NOT penalized", f_rem == [] and s_rem >= 70)

s_tv, f_tv = export.score_candidate(
    "Taylor Swift", "Love Story",
    cand("Love Story (Taylor's Version)", artist="Taylor Swift", pop=92))
check("taylor's version NOT penalized", f_tv == [] and s_tv >= 70)

s_miss, _ = export.score_candidate(
    "The Weeknd", "Blinding Lights",
    cand("Blinding Lights", artist="Some Other Artist", pop=99))
check("wrong artist sinks score", s_miss < 70)

# popularity absent (dev mode) -> still resolves by score.
c_no_pop = cand("Blinding Lights", pop=95)
del c_no_pop["popularity"]
s_np, _ = export.score_candidate("The Weeknd", "Blinding Lights", c_no_pop)
check("missing popularity degrades gracefully", s_np >= 70)

# feat. handling: mix says "Rema", candidate says "Rema feat. Selena Gomez".
s_feat, _ = export.score_candidate(
    "Rema", "Calm Down",
    {"name": "Calm Down", "uri": "spotify:track:abcd",
     "artists": [{"name": "Rema"}, {"name": "Selena Gomez"}],
     "popularity": 90})
check("feat. artist still matches", s_feat >= 70)

# ── 8. resolve_tracks ────────────────────────────────────────────────────────
fresh_env()


@with_creds
def _t_resolve():
    auth._store(21, "acc", "ref", 3600, auth.SCOPE)
    seen_queries = []

    def fake_get(path, user_id, params=None):
        seen_queries.append(params["q"])
        q = params["q"]
        if "Blinding Lights" in q and q.startswith("track:"):
            return {"tracks": {"items": [
                cand("Blinding Lights - Live", pop=50),
                cand("Blinding Lights", pop=95),
                cand("Blinding Lights (Karaoke Version)", pop=20)]}}
        if "Unknown Song XYZ" in q:
            # Qualified empty -> fallback unquoted also empty.
            return {"tracks": {"items": []}}
        return {"tracks": {"items": []}}

    with mock.patch.object(auth, "api_get", side_effect=fake_get), \
         mock.patch("time.sleep") as ms:
        uris, unresolved = export.resolve_tracks(
            [("The Weeknd", "Blinding Lights"),
             ("Nobody", "Unknown Song XYZ")], 21)
    check("resolve picks original URI",
          uris == ["spotify:track:Blin"])
    check("unresolved reported, not substituted",
          unresolved == [{"artist": "Nobody", "title": "Unknown Song XYZ"}])
    check("qualified query first",
          seen_queries[0] == 'track:"Blinding Lights" artist:"The Weeknd"')
    check("fallback to unquoted on empty",
          any(not q.startswith("track:") for q in seen_queries))
    check("no sleep after last track", ms.call_count == 1)


_t_resolve()

# ── 9. playlist create + add (Feb-2026 endpoints) ────────────────────────────
fresh_env()


@with_creds
def _t_playlist():
    auth._store(31, "acc", "ref", 3600, auth.SCOPE)
    posts = []

    def fake_post(path, user_id, json_body=None):
        posts.append((path, json_body))
        if path == "/me/playlists":
            return {"id": "pl123",
                    "external_urls": {"spotify":
                                      "https://open.spotify.com/playlist/pl123"}}
        return {"snapshot_id": "snap1"}

    with mock.patch.object(auth, "api_post", side_effect=fake_post):
        pid, url = export.create_playlist(31, "My Mix", "desc here")
        n = export.add_tracks(31, pid, ["spotify:track:a", "spotify:track:b"])
    check("create returns id+url",
          pid == "pl123" and url.endswith("/playlist/pl123"))
    create_path, create_body = posts[0]
    check("create hits POST /me/playlists (Feb-2026)",
          create_path == "/me/playlists")
    check("create payload private",
          create_body["name"] == "My Mix"
          and create_body["public"] is False
          and create_body["description"] == "desc here")
    add_path, add_body = posts[1]
    check("add hits POST /playlists/{id}/items (Feb-2026)",
          add_path == "/playlists/pl123/items")
    check("add payload uris", add_body == {"uris": ["spotify:track:a",
                                                   "spotify:track:b"]}
          and n == 2)


_t_playlist()

# ── 10. token file: perms 600 + atomic ───────────────────────────────────────
fresh_env()


@with_creds
def _t_file():
    auth._store(41, "a", "r", 3600, auth.SCOPE)
    st = os.stat(auth._TOKENS_PATH)
    check("token file mode 600",
          stat.S_IMODE(st.st_mode) == 0o600)
    check("no tmp file left behind",
          not os.path.exists(auth._TOKENS_PATH + ".tmp"))
    check("token file valid JSON with user key",
          json.load(open(auth._TOKENS_PATH)).get("41", {}).get(
              "refresh_token") == "r")
    # Corrupt file -> treated as empty, never raises.
    open(auth._TOKENS_PATH, "w").write("{not json")
    check("corrupt token file degrades",
          auth.get_stored(41) is None and auth.is_linked(41) is False)
    auth.unlink(41)  # never raises, even on corrupt file
    check("unlink never raises", True)


_t_file()

# ── 11. playlist name format ─────────────────────────────────────────────────
name = export.playlist_name("Sad Mix")
check("playlist name format",
      name.startswith("LyricsMaster · Sad Mix · ") and len(name) > 25)

# ── 12. handler-level pure helpers ───────────────────────────────────────────
# Imported from handlers to test the real glue code paths that don't need
# Telegram objects.
import handlers as H

check("code regex accepts spotify code",
      H._looks_like_spotify_code("AQD8x" + "a" * 120))
check("code regex rejects short text",
      not H._looks_like_spotify_code("hello"))
check("code regex rejects spaces",
      not H._looks_like_spotify_code("AQD code with spaces here 1234567890"))
check("code regex rejects song queries",
      not H._looks_like_spotify_code("The Weeknd - Blinding Lights"))
check("mix expiry honors TTL",
      H._spotify_mix_expired({"ts": time.time() - 7 * 3600}) is True
      and H._spotify_mix_expired({"ts": time.time()}) is False)
H._remember_spotify_mix(777, "Sad Mix",
                        [("The Weeknd", "Blinding Lights"), ("", "")])
stored_mix = H._pending_spotify_mix.get(777)
check("remember_mix stores clean tracks",
      stored_mix and stored_mix["name"] == "Sad Mix"
      and stored_mix["tracks"] == [("The Weeknd", "Blinding Lights")])
check("save button callback data",
      H._spotify_save_button()[0].callback_data == "spsave:")
import re as _re
_src = open("handlers.py").read()
check("handler_map routes spsave/spunlink",
      "'spsave': spotify_save_callback" in _src
      and "'spunlink': spotify_unlink_callback" in _src)
check("paste-code hook in natural_language_handler",
      "try_spotify_code(update, user_id, text)" in _src)
check("spotify in _KNOWN_COMMANDS", "'spotify'" in _src)

print(f"\nround73: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
