"""Round-67 tests: resilient share-card artwork (retry + no-cache-on-transient).

Covers the whole class that bit the Billie Eilish card on 2026-09-26:
a single transient blip in the iTunes lookup or the artwork download used
to silently fall back to the placeholder AND cache that broken render.

New behavior:
- fetch_artwork retries transient failures (attempts param, backoff).
- _itunes_track_lookup_strict raises on transport failure, None on no-match;
  the never-raises wrapper keeps its historic contract.
- resolve_share_artwork returns (image, transient); transient=True means
  "don't cache this render — the next share must re-attempt the artwork".
"""
import io
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers
from services import share_card as sc
from PIL import Image

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def make_png_bytes(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


PNG = make_png_bytes()


def fake_resp(content=PNG, status=200):
    m = MagicMock()
    m.content = content
    m.raise_for_status.side_effect = (
        None if status == 200 else Exception(f"HTTP {status}"))
    return m


def fake_json_resp(results):
    m = MagicMock()
    m.json.return_value = {"results": results}
    m.raise_for_status.return_value = None
    return m


def no_sleep():
    return patch.object(sc.time, "sleep", return_value=None)


# ── 1. fetch_artwork: success first try ────────────────────────────────────
with patch.object(sc.requests, "get", return_value=fake_resp()) as g, no_sleep():
    img = sc.fetch_artwork("https://x/600x600.jpg", attempts=3)
check("fetch: success returns RGB image",
      isinstance(img, Image.Image) and img.mode == "RGB")
check("fetch: success makes exactly 1 request", g.call_count == 1)

# ── 2. fetch_artwork: transient failure then success ───────────────────────
calls = {"n": 0}


def flaky_get(*a, **k):
    calls["n"] += 1
    if calls["n"] < 3:
        raise ConnectionError("blip")
    return fake_resp()


with patch.object(sc.requests, "get", side_effect=flaky_get), no_sleep():
    img2 = sc.fetch_artwork("https://x/600x600.jpg", attempts=3)
check("fetch: recovers after transient failures", isinstance(img2, Image.Image))
check("fetch: retried until success", calls["n"] == 3)

# ── 3. fetch_artwork: persistent failure -> None after all attempts ────────
with patch.object(sc.requests, "get",
                  side_effect=TimeoutError("down")) as g, \
     patch.object(sc.time, "sleep") as slp:
    img3 = sc.fetch_artwork("https://x/600x600.jpg", attempts=3)
check("fetch: persistent failure returns None", img3 is None)
check("fetch: persistent failure tries 3 times", g.call_count == 3)
check("fetch: backoff slept between attempts", slp.call_count == 2)

# ── 4. fetch_artwork: empty URL -> None, no request ────────────────────────
with patch.object(sc.requests, "get") as g:
    check("fetch: empty URL returns None", sc.fetch_artwork("") is None)
    check("fetch: empty URL makes no request", g.call_count == 0)

# ── 5. strict lookup raises on transport failure ───────────────────────────
with patch.object(handlers.requests, "get",
                  side_effect=ConnectionError("down")):
    raised = False
    try:
        handlers._itunes_track_lookup_strict("Adele", "Hello")
    except ConnectionError:
        raised = True
check("strict lookup: raises on transport failure", raised)

# ── 6. wrapper keeps never-raises contract ─────────────────────────────────
with patch.object(handlers.requests, "get",
                  side_effect=ConnectionError("down")):
    check("wrapper: transport failure -> None, no raise",
          handlers._itunes_track_lookup("Adele", "Hello") is None)

# ── 7. strict lookup: clean no-match -> None (not transient) ───────────────
with patch.object(handlers.requests, "get",
                  return_value=fake_json_resp([])):
    check("strict lookup: no results -> None",
          handlers._itunes_track_lookup_strict("Xyz", "Abc") is None)

# ── 8. resolve: lookup flaps then succeeds -> (img, False) ─────────────────
look_calls = {"n": 0}


def flaky_lookup(artist, title, timeout=None):
    look_calls["n"] += 1
    if look_calls["n"] < 3:
        raise TimeoutError("blip")
    return {"artwork": "https://x/600x600.jpg"}


with patch.object(sc.requests, "get", return_value=fake_resp()), no_sleep():
    img8, transient8 = sc.resolve_share_artwork("A", "B", flaky_lookup)
check("resolve: lookup recovers -> image", isinstance(img8, Image.Image))
check("resolve: lookup recovered -> not transient", transient8 is False)
check("resolve: lookup retried", look_calls["n"] == 3)

# ── 9. resolve: lookup dead all attempts -> (None, True) ───────────────────
def dead_lookup(artist, title, timeout=None):
    raise ConnectionError("down")


with no_sleep():
    img9, transient9 = sc.resolve_share_artwork("A", "B", dead_lookup)
check("resolve: lookup dead -> None", img9 is None)
check("resolve: lookup dead -> transient (don't cache)", transient9 is True)

# ── 10. resolve: lookup ok, no artwork -> (None, False) = cacheable ─────────
def empty_lookup(artist, title, timeout=None):
    return None


with patch.object(sc.requests, "get") as g, no_sleep():
    img10, transient10 = sc.resolve_share_artwork("A", "B", empty_lookup)
check("resolve: no artwork -> None", img10 is None)
check("resolve: no artwork -> not transient (cache placeholder)",
      transient10 is False)
check("resolve: no artwork -> no download attempted", g.call_count == 0)

# ── 11. resolve: download dead -> (None, True) ─────────────────────────────
def ok_lookup(artist, title, timeout=None):
    return {"artwork": "https://x/600x600.jpg"}


with patch.object(sc.requests, "get",
                  side_effect=TimeoutError("down")) as g, no_sleep():
    img11, transient11 = sc.resolve_share_artwork("A", "B", ok_lookup)
check("resolve: download dead -> None", img11 is None)
check("resolve: download dead -> transient (don't cache)",
      transient11 is True)
check("resolve: download retried 3 times", g.call_count == 3)

# ── 12. resolve: happy path -> (img, False) ────────────────────────────────
with patch.object(sc.requests, "get", return_value=fake_resp()), no_sleep():
    img12, transient12 = sc.resolve_share_artwork("A", "B", ok_lookup)
check("resolve: happy path -> image", isinstance(img12, Image.Image))
check("resolve: happy path -> not transient", transient12 is False)

print(f"\nround67: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
