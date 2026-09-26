"""Round 74 — Cloudflare Worker mode for Spotify OAuth.

Covers:
  - services/spotify_auth.py: lazy SPOTIFY_REDIRECT_URI / SPOTIFY_TOKEN_URL /
    SPOTIFY_WORKER_URL / SPOTIFY_WORKER_KEY env overrides, worker_configured(),
    _token_post via relay with X-Worker-Key, fetch_worker_code() shape checks.
  - handlers.py: worker-mode link prompt text, _start_spotify_link_poll,
    _poll_spotify_link success / link-error / timeout paths.

Fully mocked HTTP: ZERO real network calls. Production token/pending paths
are redirected to temp files per the round-70 lesson.

Run: python test_round74.py
"""

import os
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import spotify_auth as auth
import handlers as H

passed, failed = 0, 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


def fresh_env(**kw):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SPOTIFY_")}
    env.update({
        "SPOTIFY_CLIENT_ID": "cid",
        "SPOTIFY_CLIENT_SECRET": "csecret",
        "SPOTIFY_TOKENS_PATH": tempfile.mktemp(suffix=".json"),
        "SPOTIFY_PENDING_PATH": tempfile.mktemp(suffix=".json"),
    })
    env.update(kw)
    return env


def with_env(**kw):
    return mock.patch.dict(os.environ, fresh_env(**kw), clear=False)


# ── 1. lazy env overrides ──────────────────────────────────────────────────
with with_env():
    check("default redirect is loopback",
          auth._redirect_uri() == "http://127.0.0.1:8888/callback")
    check("default token url is direct",
          auth._token_url() == "https://accounts.spotify.com/api/token")
    check("worker not configured by default",
          auth.worker_configured() is False)

with with_env(SPOTIFY_REDIRECT_URI="https://w.workers.dev/callback",
              SPOTIFY_TOKEN_URL="https://w.workers.dev/relay/token",
              SPOTIFY_WORKER_URL="https://w.workers.dev/",
              SPOTIFY_WORKER_KEY="k123"):
    check("redirect override", auth._redirect_uri() == "https://w.workers.dev/callback")
    check("token url override", auth._token_url() == "https://w.workers.dev/relay/token")
    check("worker configured", auth.worker_configured() is True)
    check("worker base strips trailing slash", auth._worker_base() == "https://w.workers.dev")

with with_env(SPOTIFY_WORKER_URL="https://w.workers.dev"):
    check("worker needs the key too", auth.worker_configured() is False)

# ── 2. _token_post goes via relay with worker key ──────────────────────────
with with_env(SPOTIFY_WORKER_URL="https://w.workers.dev",
              SPOTIFY_WORKER_KEY="k123",
              SPOTIFY_TOKEN_URL="https://w.workers.dev/relay/token"):
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"access_token": "a", "refresh_token": "r",
                    "expires_in": 3600}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        seen["auth"] = auth
        return R()

    with mock.patch("requests.post", fake_post):
        out = auth._token_post({"grant_type": "refresh_token"})
    check("relay url used", seen["url"] == "https://w.workers.dev/relay/token")
    check("worker key header sent", seen["headers"].get("X-Worker-Key") == "k123")
    check("client_secret_basic preserved", seen["auth"] == ("cid", "csecret"))
    check("token body parsed", out["access_token"] == "a")

# direct mode: no worker header
with with_env():
    seen2 = {}

    def fake_post2(url, data=None, auth=None, headers=None, timeout=None):
        seen2["url"] = url
        seen2["headers"] = headers
        return R()

    with mock.patch("requests.post", fake_post2):
        auth._token_post({"grant_type": "x"})
    check("direct url default", seen2["url"] == "https://accounts.spotify.com/api/token")
    check("no worker header in direct mode", "X-Worker-Key" not in (seen2["headers"] or {}))

# ── 3. fetch_worker_code ───────────────────────────────────────────────────
_GOOD_CODE = "A" * 120

with with_env(SPOTIFY_WORKER_URL="https://w.workers.dev",
              SPOTIFY_WORKER_KEY="k123"):
    class R200:
        status_code = 200

        def json(self):
            return {"code": _GOOD_CODE}

    class R404:
        status_code = 404

        def json(self):
            return {"error": "not_found"}

    class R500:
        status_code = 500

        def json(self):
            return {}

    calls = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        calls["headers"] = headers
        return calls["resp"]

    with mock.patch("requests.get", fake_get):
        calls["resp"] = R200()
        got = auth.fetch_worker_code("169570389:abc123")
        check("code returned", got == _GOOD_CODE)
        check("mailbox url", calls["url"] == "https://w.workers.dev/code")
        check("state param", calls["params"] == {"state": "169570389:abc123"})
        check("key header", calls["headers"].get("X-Worker-Key") == "k123")

        calls["resp"] = R404()
        check("404 -> None", auth.fetch_worker_code("s") is None)

        calls["resp"] = R500()
        check("500 -> None", auth.fetch_worker_code("s") is None)

        class RBad:
            status_code = 200

            def json(self):
                return {"code": "not a code!!!"}

        calls["resp"] = RBad()
        check("bad shape rejected", auth.fetch_worker_code("s") is None)

    def boom(*a, **k):
        raise ConnectionError("down")

    with mock.patch("requests.get", boom):
        check("exception -> None", auth.fetch_worker_code("s") is None)

with with_env():
    check("unconfigured -> None", auth.fetch_worker_code("s") is None)

# ── 4. exchange_code sends the worker redirect_uri ─────────────────────────
with with_env(SPOTIFY_WORKER_URL="https://w.workers.dev",
              SPOTIFY_WORKER_KEY="k123",
              SPOTIFY_REDIRECT_URI="https://w.workers.dev/callback",
              SPOTIFY_TOKEN_URL="https://w.workers.dev/relay/token"):
    payload = {}

    def fake_token_post(p):
        payload.update(p)
        return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

    with mock.patch.object(auth, "_token_post", fake_token_post), \
         mock.patch.object(auth, "api_get_raw", return_value={"id": "u1", "display_name": "U"}):
        url, state = auth.build_authorize_url(4242)
        check("authorize url uses worker redirect",
              "redirect_uri=https%3A%2F%2Fw.workers.dev%2Fcallback" in url)
        info = auth.exchange_code(_GOOD_CODE, 4242)
        check("exchange posts worker redirect_uri",
              payload.get("redirect_uri") == "https://w.workers.dev/callback")
        check("linked after exchange", auth.is_linked(4242))
        check("display name", info["display_name"] == "U")

# ── 5. handlers: worker-mode prompt + poll ─────────────────────────────────
class FakeMsg:
    def __init__(self):
        self.replies = []
        self.bot = None
        self.chat_id = 999

    def reply_text(self, *a, **k):
        self.replies.append((a, k))


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, **k):
        self.sent.append((chat_id, text, k))


with with_env(SPOTIFY_WORKER_URL="https://w.workers.dev",
              SPOTIFY_WORKER_KEY="k123",
              SPOTIFY_REDIRECT_URI="https://w.workers.dev/callback"):
    # worker-mode prompt: success-page wording, no copy instructions
    m = FakeMsg()
    with mock.patch.object(H._spotify_auth, "build_authorize_url",
                           return_value=("https://auth-url", "4242:st8")):
        started = []
        with mock.patch.object(H, "_start_spotify_link_poll",
                               side_effect=lambda *a: started.append(a)):
            H._send_spotify_link_prompt(m, 4242)
    text = m.replies[0][0][0]
    check("worker prompt mentions success page", "success page" in text)
    check("worker prompt has no copy step", "Copy the whole" not in text)
    check("worker prompt starts poll", len(started) == 1 and started[0][2] == "4242:st8")

    # paste-mode prompt when worker unconfigured
    _no_worker = fresh_env()
    for _k in ("SPOTIFY_WORKER_URL", "SPOTIFY_WORKER_KEY",
               "SPOTIFY_REDIRECT_URI", "SPOTIFY_TOKEN_URL"):
        _no_worker.pop(_k, None)
    with mock.patch.dict(os.environ, _no_worker, clear=True):
        m2 = FakeMsg()
        with mock.patch.object(H._spotify_auth, "build_authorize_url",
                               return_value=("https://auth-url", "4242:st9")):
            started2 = []
            with mock.patch.object(H, "_start_spotify_link_poll",
                                   side_effect=lambda *a: started2.append(a)):
                H._send_spotify_link_prompt(m2, 4242)
        text2 = m2.replies[0][0][0]
        check("paste prompt kept as fallback", "Copy the whole address-bar URL" in text2)
        check("no poll without worker", started2 == [])

# poll success path: code arrives on 2nd check
with with_env():
    bot = FakeBot()
    calls = {"n": 0}

    def fake_fetch(state):
        calls["n"] += 1
        return None if calls["n"] < 2 else _GOOD_CODE

    with mock.patch.object(H._spotify_auth, "get_pending_link",
                           return_value={"state": "4242:st8"}), \
         mock.patch.object(H._spotify_auth, "fetch_worker_code", fake_fetch), \
         mock.patch.object(H._spotify_auth, "exchange_code",
                           return_value={"display_name": "U"}) as ex, \
         mock.patch.object(H, "_SPOTIFY_POLL_INTERVAL", 0.01), \
         mock.patch.object(H, "_SPOTIFY_POLL_TIMEOUT", 5):
        H._poll_spotify_link(bot, 999, 4242, "4242:st8")
    check("exchange called with mailbox code",
          ex.call_args[0] == (_GOOD_CODE, 4242))
    check("linked message sent",
          any("Spotify linked" in t for _, t, _ in bot.sent))
    check("only two mailbox checks", calls["n"] == 2)

# poll: superseded state exits quietly
with with_env():
    bot2 = FakeBot()
    with mock.patch.object(H._spotify_auth, "get_pending_link",
                           return_value={"state": "4242:newer"}), \
         mock.patch.object(H, "_SPOTIFY_POLL_INTERVAL", 0.01), \
         mock.patch.object(H, "_SPOTIFY_POLL_TIMEOUT", 5):
        H._poll_spotify_link(bot2, 999, 4242, "4242:st8")
    check("stale state exits silently", bot2.sent == [])

# poll: link error -> user told to re-tap
with with_env():
    bot3 = FakeBot()
    with mock.patch.object(H._spotify_auth, "get_pending_link",
                           return_value={"state": "4242:st8"}), \
         mock.patch.object(H._spotify_auth, "fetch_worker_code",
                           return_value=_GOOD_CODE), \
         mock.patch.object(H._spotify_auth, "exchange_code",
                           side_effect=H._spotify_auth.SpotifyLinkError("bad")), \
         mock.patch.object(H, "_SPOTIFY_POLL_INTERVAL", 0.01), \
         mock.patch.object(H, "_SPOTIFY_POLL_TIMEOUT", 5):
        H._poll_spotify_link(bot3, 999, 4242, "4242:st8")
    check("link error message sent",
          any("didn't go through" in t for _, t, _ in bot3.sent))

# poll: timeout -> gentle nudge
with with_env():
    bot4 = FakeBot()
    with mock.patch.object(H._spotify_auth, "get_pending_link",
                           return_value={"state": "4242:st8"}), \
         mock.patch.object(H._spotify_auth, "fetch_worker_code",
                           return_value=None), \
         mock.patch.object(H, "_SPOTIFY_POLL_INTERVAL", 0.01), \
         mock.patch.object(H, "_SPOTIFY_POLL_TIMEOUT", 0.05):
        H._poll_spotify_link(bot4, 999, 4242, "4242:st8")
    check("timeout nudge sent",
          any("didn't catch a Spotify approval" in t for _, t, _ in bot4.sent))

print(f"\nround74: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
