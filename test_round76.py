"""Round 76: Spotify save — survive the create→add 404 race, stay atomic.

Regression test for the 2026-09-26 /top kpop wild failure: the playlist
was created, then POST /playlists/{id}/items returned 404 because the new
playlist id wasn't writable yet (Spotify propagation lag). Fixes:

  1. add_tracks retries a 404 a few times with a pause (only 404 —
     auth/rate-limit/bad-request errors surface immediately).
  2. save_playlist() wraps create+add atomically: if the add fails, the
     just-created playlist is unfollowed (deleted) so a failed save never
     leaves an empty orphan. Cleanup is best-effort and never masks the
     original error.

All network access is mocked; time.sleep is stubbed so the suite is fast.
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


def _err404():
    return auth.SpotifyAPIError("POST /playlists/pid/items -> 404", status=404)


def _err500():
    return auth.SpotifyAPIError("POST /playlists/pid/items -> 500", status=500)


_UID = 169570389
_URIS = ["spotify:track:aaa", "spotify:track:bbb"]


def _ctx(api_post=None, api_delete=None, create=None):
    """Build the patch context for one scenario."""
    patches = [mock.patch.object(export.time, "sleep")]
    if api_post is not None:
        patches.append(mock.patch.object(export.auth, "api_post", api_post))
    if api_delete is not None:
        patches.append(mock.patch.object(export.auth, "api_delete", api_delete))
    if create is not None:
        patches.append(mock.patch.object(export, "create_playlist", create))
    return patches


def _run(patches, fn):
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in reversed(patches):
            p.stop()


# 1. 404 then success: one retry, then the add lands, no cleanup -----------
calls = {"post": 0, "sleep": 0}


def _flaky_post(path, user_id, json_body=None):
    calls["post"] += 1
    if calls["post"] == 1:
        raise _err404()
    return {"snapshot_id": "snap1"}


def _count_sleep(s):
    calls["sleep"] += 1


with mock.patch.object(export.time, "sleep", _count_sleep), \
     mock.patch.object(export.auth, "api_post", _flaky_post):
    added = export.add_tracks(_UID, "pid", _URIS)
check("404-then-success: add_tracks returns track count", added == 2)
check("404-then-success: retried exactly once", calls["post"] == 2)
check("404-then-success: paused once between attempts", calls["sleep"] == 1)

# 2. Persistent 404: raises, orphan playlist is deleted ----------------------
posted = []
deleted = []


def _always404(path, user_id, json_body=None):
    posted.append(path)
    raise _err404()


def _ok_delete(path, user_id):
    deleted.append(path)
    return {}


def _fake_create(user_id, name, description=""):
    return "pid", "https://open.spotify.com/playlist/pid"


def scenario2():
    try:
        export.save_playlist(_UID, "n", "d", _URIS)
        return "no-raise"
    except auth.SpotifyAPIError as e:
        return e


err = _run(_ctx(api_post=_always404, api_delete=_ok_delete,
                create=_fake_create), scenario2)
check("persistent 404: original SpotifyAPIError propagates",
      isinstance(err, auth.SpotifyAPIError) and err.status == 404)
check("persistent 404: retried up to the limit",
      len(posted) == export._ADD_404_RETRIES)
check("persistent 404: orphan playlist unfollowed",
      deleted == ["/playlists/pid/followers"])

# 3. Cleanup failure never masks the original error ---------------------------
def _boom_delete(path, user_id):
    raise RuntimeError("delete exploded")


def scenario3():
    try:
        export.save_playlist(_UID, "n", "d", _URIS)
        return "no-raise"
    except Exception as e:  # noqa: BLE001 — asserting the type below
        return e


err = _run(_ctx(api_post=_always404, api_delete=_boom_delete,
                create=_fake_create), scenario3)
check("cleanup failure: original 404 still propagates (not RuntimeError)",
      isinstance(err, auth.SpotifyAPIError) and err.status == 404)

# 4. Non-404 errors are NOT retried, but still clean up -----------------------
posted500 = []
deleted500 = []


def _always500(path, user_id, json_body=None):
    posted500.append(path)
    raise _err500()


def _ok_delete500(path, user_id):
    deleted500.append(path)
    return {}


def scenario4():
    try:
        export.save_playlist(_UID, "n", "d", _URIS)
        return "no-raise"
    except auth.SpotifyAPIError as e:
        return e


err = _run(_ctx(api_post=_always500, api_delete=_ok_delete500,
                create=_fake_create), scenario4)
check("500: surfaces immediately without retry", len(posted500) == 1)
check("500: propagates with its status",
      isinstance(err, auth.SpotifyAPIError) and err.status == 500)
check("500: orphan still cleaned up",
      deleted500 == ["/playlists/pid/followers"])

# 5. Happy path: create + add, no delete -------------------------------------
deleted_hp = []
posted_hp = []


def _ok_post(path, user_id, json_body=None):
    posted_hp.append(path)
    return {"snapshot_id": "snap"}


def _spy_delete(path, user_id):
    deleted_hp.append(path)
    return {}


def scenario5():
    return export.save_playlist(_UID, "My Mix", "d", _URIS)


out = _run(_ctx(api_post=_ok_post, api_delete=_spy_delete,
                create=_fake_create), scenario5)
check("happy path: returns (pid, url, added)",
      out == ("pid", "https://open.spotify.com/playlist/pid", 2))
check("happy path: single add call, no retry", len(posted_hp) == 1)
check("happy path: no cleanup attempted", deleted_hp == [])

print(f"\nround76: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
