"""Spotify OAuth (Authorization Code + PKCE) for the Export feature.

Round 73. This module owns the *user* token lifecycle: linking a user's
Spotify account, persisting access/refresh tokens, and silently refreshing
expired access tokens. It has no Telegram imports.

Design notes:
  - Authorization Code + PKCE is REQUIRED (not optional): the pasted
    authorization code travels through Telegram chat, so the code alone
    must be worthless without the code_verifier, which never leaves this
    machine.
  - There is no public callback endpoint on this VM (no inbound network).
    Round 74 adds an optional Cloudflare Worker (see ../spotify-worker/):
    when SPOTIFY_WORKER_URL/KEY are set, the redirect URI becomes the
    Worker's public /callback (pretty success page, no copy-paste) and the
    token endpoint becomes the Worker's /relay/token (the VM's egress
    proxy blocks accounts.spotify.com/api/token directly). Without the
    Worker env vars the module falls back to the loopback redirect +
    paste-the-code flow.
  - Client credentials are read LAZILY from the environment at call time,
    so adding SPOTIFY_CLIENT_ID/SECRET to .env later needs no restart.
  - Token storage is an untracked runtime file (``.spotify_tokens.json``,
    chmod 600, atomic writes), keyed by Telegram user id. Token values
    are NEVER logged. Tests must patch ``_TOKENS_PATH`` / ``_PENDING_PATH``
    to temp files — never touch the production paths.
  - Built against the February 2026 Web API migration (verified 2026-09-26):
    playlist create/add endpoints, search limits, stripped fields. All
    Spotify-specific constants live here so the next API change is a
    one-file patch.
"""

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# ── Spotify endpoints / constants (Feb-2026 shapes) ──────────────────────────
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
# Direct token endpoint. UNREACHABLE from this VM: the egress proxy answers
# POSTs to it with {"error":"refresh_rejected"} (verified 2026-09-26), so in
# production these go through the Cloudflare Worker relay instead — see
# SPOTIFY_TOKEN_URL below. The default is kept for local dev / tests.
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
# Default loopback redirect, registered in the Spotify dashboard.
# 'localhost' hostnames are rejected by Spotify; the numeric loopback is not.
_LOOPBACK_REDIRECT = "http://127.0.0.1:8888/callback"
# Kept as a module constant for backwards compatibility; production code
# must call _redirect_uri() so the Worker callback can be configured.
REDIRECT_URI = _LOOPBACK_REDIRECT
SCOPE = "playlist-modify-private"


def _redirect_uri() -> str:
    """Redirect URI actually used (Worker callback when configured)."""
    return os.environ.get("SPOTIFY_REDIRECT_URI") or _LOOPBACK_REDIRECT


def _token_url() -> str:
    """Token endpoint actually used (Worker relay when configured)."""
    return os.environ.get("SPOTIFY_TOKEN_URL") or TOKEN_URL


def _worker_base() -> str:
    """Cloudflare Worker base URL, e.g. https://x.workers.dev ('' if unset)."""
    return (os.environ.get("SPOTIFY_WORKER_URL") or "").rstrip("/")


def _worker_key() -> str:
    return os.environ.get("SPOTIFY_WORKER_KEY") or ""


def worker_configured() -> bool:
    """True when the Worker relay/callback mode is fully configured."""
    return bool(_worker_base() and _worker_key())


# Authorization codes are ~200+ chars of [A-Za-z0-9_-]; used to sanity-check
# values coming back from the Worker mailbox (never trust remote input).
_CODE_SHAPE = re.compile(r"^[A-Za-z0-9_-]{40,512}$")

_HTTP_TIMEOUT = 15
# Treat tokens expiring within this window as expired (clock skew buffer).
_EXPIRY_SKEW = 120
# A pasted-code link flow older than this is dead (user must re-tap Link).
_LINK_TTL = 15 * 60

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_TOKENS_PATH = os.environ.get(
    "SPOTIFY_TOKENS_PATH", os.path.join(_BASE_DIR, ".spotify_tokens.json"))
_PENDING_PATH = os.environ.get(
    "SPOTIFY_PENDING_PATH", os.path.join(_BASE_DIR, ".spotify_pending.json"))

_lock = threading.RLock()

# In-memory pending link flows: user_id -> {verifier, state, created_at}.
# Mirrored to _PENDING_PATH so a restart doesn't strand a linking user.
_pending_links = {}


# ── Exceptions ───────────────────────────────────────────────────────────────
class SpotifyError(Exception):
    """Base for all Spotify auth/export errors."""


class SpotifyNotConfigured(SpotifyError):
    """SPOTIFY_CLIENT_ID/SECRET are not in the environment yet."""


class SpotifyUnlinked(SpotifyError):
    """No usable token for this user (never linked, or revoked)."""


class SpotifyLinkError(SpotifyError):
    """The link/paste-code flow failed (expired, mismatched, bad code)."""


class SpotifyAPIError(SpotifyError):
    """A Spotify API call failed after retries."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# ── Client credentials (lazy) ────────────────────────────────────────────────
def _client_id():
    return os.environ.get("SPOTIFY_CLIENT_ID") or ""


def _client_secret():
    return os.environ.get("SPOTIFY_CLIENT_SECRET") or ""


def is_configured() -> bool:
    """True when the Spotify app credentials are present."""
    return bool(_client_id() and _client_secret())


def _require_configured():
    if not is_configured():
        raise SpotifyNotConfigured(
            "SPOTIFY_CLIENT_ID/SECRET are not set in the environment.")


# ── PKCE ─────────────────────────────────────────────────────────────────────
def pkce_pair():
    """Return (verifier, S256 challenge)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ── Pending-link store ───────────────────────────────────────────────────────
def _load_pendings():
    try:
        with open(_PENDING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pendings(data):
    try:
        tmp = _PENDING_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, _PENDING_PATH)
        try:
            os.chmod(_PENDING_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[spotify] pending-link save failed: {e}")


def _prune_pendings(now=None):
    now = now if now is not None else time.time()
    dead = [u for u, p in _pending_links.items()
            if now - p.get("created_at", 0) > _LINK_TTL]
    for u in dead:
        _pending_links.pop(u, None)
    if dead:
        _save_pendings(_pending_links)


def build_authorize_url(user_id) -> tuple:
    """Start a link flow. Returns (authorize_url, state).

    The code_verifier is kept server-side in the pending-link store; only
    the challenge travels in the URL.
    """
    _require_configured()
    verifier, challenge = pkce_pair()
    state = f"{user_id}:{secrets.token_hex(8)}"
    with _lock:
        if not _pending_links:
            # Warm from disk on first use after a restart.
            for u, p in _load_pendings().items():
                _pending_links[u] = p
        _pending_links[str(user_id)] = {
            "verifier": verifier, "state": state,
            "created_at": time.time(),
        }
        _prune_pendings()
        _save_pendings(_pending_links)
    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": SCOPE,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
    }
    url = AUTHORIZE_URL + "?" + urlencode(params)
    logger.info(f"[spotify] link flow started for user {user_id}")
    return url, state


def get_pending_link(user_id):
    """Return the pending link dict, or None if absent/expired. Never raises."""
    try:
        with _lock:
            if not _pending_links:
                for u, p in _load_pendings().items():
                    _pending_links[u] = p
            _prune_pendings()
            return _pending_links.get(str(user_id))
    except Exception:
        return None


def _drop_pending(user_id):
    with _lock:
        _pending_links.pop(str(user_id), None)
        _save_pendings(_pending_links)


def fetch_worker_code(state: str):
    """Poll the Worker mailbox for the authorization code for `state`.

    Round 74: after the user approves on Spotify they land on the Worker's
    success page; the Worker stashes the code in KV keyed by state and the
    bot picks it up here. Returns the code string, or None when nothing is
    there yet / the Worker isn't configured / anything fails. Never raises,
    never logs the code.
    """
    try:
        if not worker_configured() or not state:
            return None
        resp = requests.get(
            _worker_base() + "/code",
            params={"state": state},
            headers={"X-Worker-Key": _worker_key()},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning(f"[spotify] worker /code -> {resp.status_code}")
            return None
        code = ((resp.json() or {}).get("code") or "").strip()
        return code if _CODE_SHAPE.match(code) else None
    except Exception as e:
        logger.warning(f"[spotify] worker /code fetch failed: {e}")
        return None


# ── Token store ──────────────────────────────────────────────────────────────
def _load_tokens() -> dict:
    try:
        with open(_TOKENS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tokens(data: dict) -> None:
    tmp = _TOKENS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _TOKENS_PATH)
    try:
        os.chmod(_TOKENS_PATH, 0o600)
    except Exception:
        pass


def get_stored(user_id):
    """Return the stored token dict for a user, or None. Never raises."""
    try:
        with _lock:
            return _load_tokens().get(str(user_id))
    except Exception:
        return None


def is_linked(user_id) -> bool:
    tok = get_stored(user_id)
    return bool(tok and tok.get("refresh_token"))


def _store(user_id, access_token, refresh_token, expires_in, scope,
           spotify_user_id=None, display_name=None):
    with _lock:
        data = _load_tokens()
        data[str(user_id)] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + max(0, int(expires_in or 0)),
            "scope": scope or SCOPE,
            "spotify_user_id": spotify_user_id,
            "display_name": display_name,
        }
        _save_tokens(data)


def unlink(user_id) -> None:
    """Delete a user's stored tokens. Never raises."""
    try:
        with _lock:
            data = _load_tokens()
            data.pop(str(user_id), None)
            _save_tokens(data)
        logger.info(f"[spotify] unlinked user {user_id}")
    except Exception as e:
        logger.warning(f"[spotify] unlink failed: {e}")


# ── Token exchange / refresh ─────────────────────────────────────────────────
def _token_post(payload: dict) -> dict:
    """POST to the token endpoint with client_secret_basic. Never logs secrets.

    Round 74: when the Worker relay is configured the POST goes to the
    relay (which forwards it to Spotify from Cloudflare's network), with
    the shared worker key as an extra header.
    """
    headers = {}
    if worker_configured():
        headers["X-Worker-Key"] = _worker_key()
    resp = requests.post(
        _token_url(),
        data=payload,
        auth=(_client_id(), _client_secret()),
        headers=headers,
        timeout=_HTTP_TIMEOUT,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code != 200:
        raise SpotifyLinkError(
            f"token endpoint returned {resp.status_code}: "
            f"{body.get('error', 'unknown error')}")
    return body


def exchange_code(code: str, user_id) -> dict:
    """Exchange a pasted authorization code for tokens.

    Validates the pending link flow for this user, then stores the token
    pair. Returns {"spotify_user_id", "display_name"} (values may be None
    if /me is unreachable — linking still counts).
    """
    _require_configured()
    code = (code or "").strip()
    if not code:
        raise SpotifyLinkError("empty code")
    pending = get_pending_link(user_id)
    if not pending:
        raise SpotifyLinkError(
            "no pending link flow (expired or never started)")
    body = _token_post({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
        "code_verifier": pending["verifier"],
    })
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        raise SpotifyLinkError("token endpoint did not return a token pair")
    _drop_pending(user_id)
    # Best-effort: learn who just linked (dev-mode /me keeps id/display_name).
    spotify_user_id, display_name = None, None
    try:
        me = api_get_raw("/me", access)
        spotify_user_id = me.get("id")
        display_name = me.get("display_name")
    except Exception as e:
        logger.warning(f"[spotify] /me lookup failed (non-fatal): {e}")
    _store(user_id, access, refresh, body.get("expires_in", 3600),
           body.get("scope", SCOPE), spotify_user_id, display_name)
    logger.info(f"[spotify] user {user_id} linked successfully")
    return {"spotify_user_id": spotify_user_id, "display_name": display_name}


def _refresh_locked(user_id, refresh_token) -> str:
    """Refresh inside _lock. Returns the new access token."""
    try:
        body = _token_post({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
    except SpotifyLinkError as e:
        if "invalid_grant" in str(e):
            unlink(user_id)
            raise SpotifyUnlinked(
                "Spotify access was revoked — please link again.")
        raise
    access = body.get("access_token")
    if not access:
        raise SpotifyLinkError("refresh did not return an access token")
    # Spotify may or may not rotate the refresh token; keep the old one
    # when the response doesn't include a new one.
    new_refresh = body.get("refresh_token") or refresh_token
    with _lock:
        data = _load_tokens()
        cur = data.get(str(user_id)) or {}
        cur.update({
            "access_token": access,
            "refresh_token": new_refresh,
            "expires_at": time.time() + max(0, int(body.get("expires_in", 3600))),
            "scope": body.get("scope", cur.get("scope", SCOPE)),
        })
        _save_tokens(data)
    logger.info(f"[spotify] refreshed access token for user {user_id}")
    return access


def ensure_access_token(user_id) -> str:
    """Return a valid access token, refreshing silently when needed."""
    _require_configured()
    with _lock:
        tok = (_load_tokens().get(str(user_id))) or {}
        access = tok.get("access_token")
        refresh = tok.get("refresh_token")
        if not access or not refresh:
            raise SpotifyUnlinked("Spotify is not linked for this user.")
        if tok.get("expires_at", 0) - time.time() > _EXPIRY_SKEW:
            return access
        return _refresh_locked(user_id, refresh)


# ── API helpers ──────────────────────────────────────────────────────────────
def api_get_raw(path: str, access_token: str, params=None) -> dict:
    """GET with an explicit token (used pre-link for /me)."""
    resp = requests.get(API_BASE + path,
                        headers={"Authorization": f"Bearer {access_token}"},
                        params=params or {}, timeout=_HTTP_TIMEOUT)
    if resp.status_code == 401:
        raise SpotifyUnlinked("token rejected")
    if resp.status_code == 429:
        _backoff(resp)
        resp = requests.get(API_BASE + path,
                            headers={"Authorization": f"Bearer {access_token}"},
                            params=params or {}, timeout=_HTTP_TIMEOUT)
    if resp.status_code >= 400:
        raise SpotifyAPIError(f"GET {path} -> {resp.status_code}",
                              status=resp.status_code)
    return resp.json()


def _backoff(resp):
    try:
        wait = min(float(resp.headers.get("Retry-After", "2")), 5)
    except Exception:
        wait = 2
    logger.info(f"[spotify] 429 — backing off {wait}s")
    time.sleep(wait)


def _do_request(method, path, user_id, json_body=None, params=None,
               _force_refreshed=False):
    token = ensure_access_token(user_id)
    if _force_refreshed:
        # A 401 already happened: force a fresh token before retrying.
        with _lock:
            tok = (_load_tokens().get(str(user_id))) or {}
            token = _refresh_locked(user_id, tok.get("refresh_token"))
    resp = requests.request(
        method, API_BASE + path,
        headers={"Authorization": f"Bearer {token}"},
        json=json_body, params=params or {}, timeout=_HTTP_TIMEOUT)
    if resp.status_code == 401 and not _force_refreshed:
        logger.info(f"[spotify] 401 on {method} {path} — refreshing once")
        return _do_request(method, path, user_id, json_body, params,
                           _force_refreshed=True)
    if resp.status_code == 401:
        unlink(user_id)
        raise SpotifyUnlinked(
            "Spotify rejected the token — please link again.")
    if resp.status_code == 429:
        _backoff(resp)
        resp = requests.request(
            method, API_BASE + path,
            headers={"Authorization": f"Bearer {token}"},
            json=json_body, params=params or {}, timeout=_HTTP_TIMEOUT)
    if resp.status_code >= 400:
        raise SpotifyAPIError(f"{method} {path} -> {resp.status_code}",
                              status=resp.status_code)
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


def api_get(path: str, user_id, params=None) -> dict:
    return _do_request("GET", path, user_id, params=params)


def api_post(path: str, user_id, json_body=None) -> dict:
    return _do_request("POST", path, user_id, json_body=json_body)


def api_delete(path: str, user_id) -> dict:
    return _do_request("DELETE", path, user_id)
