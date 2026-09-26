"""Resolve bot mixes to exact Spotify tracks and save them as playlists.

Round 73. Depends on spotify_auth for tokens; has no Telegram imports.

Matching philosophy: a wrong track in the user's library is worse than a
missing one. Candidates are scored 0-100; only the best candidate at or
above _ACCEPT_SCORE is accepted, everything else is reported as
unresolved — never silently substituted.

Built against the February 2026 Web API migration (verified 2026-09-26):
  - search:  GET /search?type=track&limit<=10&market=US
  - create:  POST /me/playlists {name, public, description}
  - add:     POST /playlists/{id}/items {uris}  (<=100 per call)
  - NO batch GET /tracks?ids= — tracks are resolved one search at a time.
  - track `popularity` may be absent in dev mode: used as a tiebreak only
    when present, never required.
"""

import logging
import re
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from . import spotify_auth as auth

logger = logging.getLogger(__name__)

_ACCEPT_SCORE = 70
_SEARCH_LIMIT = 10
_SEARCH_SLEEP = 0.2  # politeness pause between per-track searches
_ADD_CHUNK = 100
# A freshly created playlist can 404 on the items endpoint until Spotify's
# backend propagates it (seen in the wild 2026-09-26, round 76): retry the
# failing add a few times with a pause before giving up.
_ADD_404_RETRIES = 3
_ADD_404_BACKOFF = 2.0  # seconds between retries


# ── Normalization ────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    """Lowercase, strip diacritics, drop punctuation, collapse spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _base_title(title: str) -> str:
    """Title with parenthetical/bracket qualifiers removed for comparison."""
    t = re.sub(r"\([^()]*\)", " ", title or "")
    t = re.sub(r"\[[^\[\]]*\]", " ", t)
    return _normalize(t)


def _artist_key(artist: str) -> str:
    """Artist with feat./ft./with clauses stripped for comparison."""
    a = re.sub(r"\s+(feat\.?|ft\.?|with|vs\.?)\s+.*$", "", artist or "",
               flags=re.IGNORECASE)
    return _normalize(a)


# ── Candidate penalties (applied to the RAW candidate title, normalized) ────
# A penalty only fires on the candidate side: the bot's own mix titles are
# already de-noised upstream.
_PENALTIES = [
    (re.compile(r"\bkaraoke\b"), -50, "karaoke"),
    (re.compile(r"\b(cover|tribute)\b"), -50, "cover/tribute"),
    (re.compile(r"\b(live|unplugged)\b"), -40, "live"),
    (re.compile(r"\bdemo\b"), -30, "demo"),
    (re.compile(r"(sped ?up|slowed|8d|nightcore|slowed ?\+ ?reverb)"), -25,
     "altered"),
    (re.compile(r"\bacoustic\b"), -15, "acoustic"),
    (re.compile(r"\binstrumental\b"), -20, "instrumental"),
]
# Deliberately NOT penalized: remaster(ed) — same recording; re-recordings
# ("Taylor's Version") — arguably the correct current version.


def score_candidate(artist: str, title: str, candidate: dict):
    """Score a Spotify track candidate 0-100. Returns (score, flags).

    flags is a sorted list of penalty labels that fired (for tiebreaks and
    debugging). Never raises — a malformed candidate scores 0.
    """
    try:
        cand_artists = candidate.get("artists") or []
        cand_names = [_artist_key(a.get("name", "")) for a in cand_artists]
        want_artist = _artist_key(artist)
        if want_artist and want_artist in cand_names:
            artist_score = 1.0
        else:
            # Partial credit for token overlap ("The Weeknd" vs "Weeknd").
            best = 0.0
            want_tokens = set(want_artist.split())
            for cn in cand_names:
                cn_tokens = set(cn.split())
                if want_tokens and cn_tokens:
                    overlap = len(want_tokens & cn_tokens) / max(
                        len(want_tokens), len(cn_tokens))
                    best = max(best, overlap)
            artist_score = best

        cand_title = candidate.get("name", "")
        want_base, cand_base = _base_title(title), _base_title(cand_title)
        if want_base and want_base == cand_base:
            title_score = 1.0
        else:
            title_score = SequenceMatcher(None, want_base, cand_base).ratio()

        score = 50.0 * artist_score + 50.0 * title_score

        raw = _normalize(cand_title)
        flags = []
        for rx, penalty, label in _PENALTIES:
            if rx.search(raw):
                score += penalty
                flags.append(label)
        return max(0, round(score)), sorted(flags)
    except Exception as e:
        logger.warning(f"[spotify] score_candidate failed: {e}")
        return 0, ["error"]


# ── Search ───────────────────────────────────────────────────────────────────
def search_candidates(artist: str, title: str, user_id):
    """Return raw Spotify track candidates for one song.

    Qualified query first (precision); unquoted fallback when it is empty.
    """
    qualified = f'track:"{title}" artist:"{artist}"'
    items = _search(qualified, user_id)
    if not items:
        items = _search(f"{title} {artist}", user_id)
    return items


def _search(query: str, user_id):
    try:
        data = auth.api_get("/search", user_id,
                            params={"q": query, "type": "track",
                                    "limit": _SEARCH_LIMIT, "market": "US"})
        return ((data.get("tracks") or {}).get("items")) or []
    except auth.SpotifyError:
        raise
    except Exception as e:
        logger.warning(f"[spotify] search failed for {query!r}: {e}")
        return []


def resolve_tracks(tracks, user_id):
    """Resolve [(artist, title)] to Spotify URIs.

    Returns (uris, unresolved) where unresolved is a list of
    {"artist", "title"} dicts that could not be matched confidently.
    """
    uris, unresolved = [], []
    total = len(tracks)
    for i, (artist, title) in enumerate(tracks, 1):
        try:
            candidates = search_candidates(artist, title, user_id)
            scored = []
            for c in candidates:
                score, flags = score_candidate(artist, title, c)
                # popularity may be absent in dev mode — degrade gracefully.
                pop = c.get("popularity")
                pop = pop if isinstance(pop, (int, float)) else 0
                scored.append((score, pop, len(flags), c))
            scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
            if scored and scored[0][0] >= _ACCEPT_SCORE:
                uris.append(scored[0][3]["uri"])
                logger.info(
                    f"[spotify] matched {i}/{total}: '{artist} - {title}' "
                    f"-> score {scored[0][0]}")
            else:
                best = scored[0][0] if scored else 0
                logger.info(
                    f"[spotify] unresolved {i}/{total}: '{artist} - {title}' "
                    f"(best score {best})")
                unresolved.append({"artist": artist, "title": title})
        except auth.SpotifyError:
            raise
        except Exception as e:
            logger.warning(f"[spotify] resolve failed for "
                           f"'{artist} - {title}': {e}")
            unresolved.append({"artist": artist, "title": title})
        if i < total:
            time.sleep(_SEARCH_SLEEP)
    return uris, unresolved


# ── Playlists (Feb-2026 endpoint shapes) ─────────────────────────────────────
def playlist_name(mix_name: str) -> str:
    """'LyricsMaster · Sad Mix · Sep 26' (user-local date, Asia/Kuwait)."""
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Kuwait")).strftime("%b %d")
    except Exception:
        today = datetime.now().strftime("%b %d")
    return f"LyricsMaster · {mix_name} · {today}"


def create_playlist(user_id, name: str, description: str = ""):
    """Create a PRIVATE playlist. Returns (playlist_id, open_url)."""
    data = auth.api_post("/me/playlists", user_id, json_body={
        "name": name,
        "public": False,
        "description": description or "Made with LyricsMaster 🎵",
    })
    pid = data.get("id")
    url = ((data.get("external_urls") or {}).get("spotify")) or ""
    if not pid:
        raise auth.SpotifyAPIError("playlist creation returned no id")
    logger.info(f"[spotify] created playlist '{name}' ({pid}) for user {user_id}")
    return pid, url


def add_tracks(user_id, playlist_id: str, uris) -> int:
    """Add URIs to a playlist (chunked at 100). Returns tracks added."""
    uris = list(uris or [])
    added = 0
    for i in range(0, len(uris), _ADD_CHUNK):
        chunk = uris[i:i + _ADD_CHUNK]
        _post_items_with_retry(user_id, playlist_id, chunk)
        added += len(chunk)
    logger.info(f"[spotify] added {added} tracks to {playlist_id}")
    return added


def _post_items_with_retry(user_id, playlist_id: str, chunk) -> None:
    """POST one chunk of URIs, retrying a 404 a few times.

    Only 404 is retried: it means the playlist id the create call just
    returned isn't writable yet (propagation lag). Any other error
    (auth, rate limit, bad request) surfaces immediately.
    """
    last = None
    for attempt in range(_ADD_404_RETRIES):
        try:
            auth.api_post(f"/playlists/{playlist_id}/items", user_id,
                          json_body={"uris": chunk})
            if attempt:
                logger.info(
                    f"[spotify] add to {playlist_id} recovered "
                    f"after {attempt} retr{'y' if attempt == 1 else 'ies'}")
            return
        except auth.SpotifyAPIError as e:
            last = e
            if e.status == 404 and attempt < _ADD_404_RETRIES - 1:
                logger.warning(
                    f"[spotify] add -> 404 (attempt {attempt + 1}/"
                    f"{_ADD_404_RETRIES}); retrying in {_ADD_404_BACKOFF}s "
                    f"(playlist {playlist_id} may still be propagating)")
                time.sleep(_ADD_404_BACKOFF)
            else:
                raise
    raise last  # unreachable: the loop always returns or raises


def save_playlist(user_id, name: str, description: str, uris):
    """Create a private playlist and add URIs, atomically.

    If adding tracks fails, the just-created playlist is unfollowed
    (deleted) so a failed save never leaves an empty orphan behind.
    Cleanup is best-effort: a failed cleanup is logged and never masks
    the original error. Returns (playlist_id, open_url, tracks_added).
    """
    pid, url = create_playlist(user_id, name, description)
    try:
        added = add_tracks(user_id, pid, uris)
    except Exception:
        _delete_playlist_quietly(user_id, pid)
        raise
    return pid, url, added


def _delete_playlist_quietly(user_id, playlist_id: str) -> None:
    """Best-effort removal of a playlist we just created. Never raises."""
    try:
        auth.api_delete(f"/playlists/{playlist_id}/followers", user_id)
        logger.info(f"[spotify] removed orphan playlist {playlist_id} "
                    f"after failed save")
    except Exception as e:
        logger.warning(f"[spotify] orphan cleanup failed for "
                       f"{playlist_id}: {e}")
