"""Round-68 tests: translation fallback + 429 circuit breaker.

The 2026-09-26 incident: Google's free gtx endpoint 429-rate-limited this
egress IP for 20+ minutes. The old code retried the same doomed endpoint
(2s/4s backoff can't clear a rate-limit wave) and the user got "service
unavailable — try again" even after retrying manually.

New behavior:
- translate_chunk: Google first, OpenAI fallback when Google fails.
- 429 circuit breaker: 3 consecutive 429s -> Google treated as down for
  15min, chunks go straight to OpenAI (no doomed retries, no ban-storm).
- Success-only cache still holds; failures never poison it.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import translator_service as ts

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def reset():
    ts._chunk_cache.clear()
    ts._gtx_breaker["consec_429"] = 0
    ts._gtx_breaker["until"] = 0.0


def _chunk_boundaries_on_lines(body, chunks):
    """True iff every chunk boundary in `body` sits on a line break —
    i.e. no chunk ever cuts a word in half."""
    pos = 0
    for i, c in enumerate(chunks):
        if body[pos:pos + len(c)] != c:
            return False
        pos += len(c)
        if i < len(chunks) - 1:
            if pos >= len(body) or body[pos] != "\n":
                return False
            pos += 1  # skip the separator newline
    return pos == len(body)


def gtx_ok(text="مرحبا"):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = [[[text, "hello"]]]
    return m


def http_error(status):
    resp = MagicMock()
    resp.status_code = status
    err = requests.HTTPError(f"{status} Client Error")
    err.response = resp
    return err


def fake_openai(text="ترجمة"):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(output_text=text)
    return client


def no_sleep():
    return patch.object(ts.time, "sleep", return_value=None)


# ── 1. Google success: OpenAI never touched ─────────────────────────────────
reset()
oa = fake_openai()
with patch.object(ts.requests, "get", return_value=gtx_ok("أهلا")) as g, \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    check("google ok: returns translation",
          ts.translate_chunk("hello", "ar") == "أهلا")
    check("google ok: OpenAI not called",
          oa.responses.create.call_count == 0)

# ── 2. Google 429s -> OpenAI fallback fires ─────────────────────────────────
reset()
oa = fake_openai("بديل")
with patch.object(ts.requests, "get",
                  side_effect=http_error(429)) as g, \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    out = ts.translate_chunk("hello", "ar")
check("429 wave: fallback returns translation", out == "بديل")
check("429 wave: OpenAI was called", oa.responses.create.call_count == 1)

# ── 3. Breaker trips after 3 consecutive 429s: next chunk skips Google ──────
reset()
oa = fake_openai("ب")
with patch.object(ts.requests, "get",
                  side_effect=http_error(429)) as g, \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    ts.translate_chunk("one", "ar")   # 3 attempts -> 3 consecutive 429s
    check("breaker: tripped after 3x429", ts._gtx_breaker["until"] > 0)
    g.reset_mock()
    out2 = ts.translate_chunk("two", "ar")
    check("breaker: Google skipped while cooling down", g.call_count == 0)
    check("breaker: fallback still serves", out2 == "ب")

# ── 4. Cooldown expiry: Google is tried again ───────────────────────────────
reset()
ts._gtx_breaker["until"] = ts.time.time() - 1  # expired
oa = fake_openai()
with patch.object(ts.requests, "get", return_value=gtx_ok("رجع")) as g, \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    check("cooldown expired: Google tried again",
          ts.translate_chunk("hello", "ar") == "رجع")
    check("cooldown expired: actually called", g.call_count == 1)

# ── 5. Success resets the 429 counter (no trip on intermittent 429s) ────────
reset()
oa = fake_openai("ب")
seq = [http_error(429), http_error(429), gtx_ok("ok"),
       http_error(429), http_error(429), gtx_ok("ok2")]
with patch.object(ts.requests, "get", side_effect=seq), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    ts.translate_chunk("a", "ar")
    ts._chunk_cache.clear()
    ts.translate_chunk("b", "ar")
check("intermittent 429s: breaker never trips",
      ts._gtx_breaker["until"] == 0.0)

# ── 6. Both backends dead -> None (honest failure) ─────────────────────────
reset()
dead_oa = MagicMock()
dead_oa.responses.create.side_effect = Exception("openai down")
with patch.object(ts.requests, "get",
                  side_effect=http_error(429)), \
     patch.object(ts, "_get_openai_client", return_value=dead_oa), no_sleep():
    check("both dead: returns None",
          ts.translate_chunk("hello", "ar") is None)

# ── 7. No OpenAI key + Google 429 -> None, graceful ────────────────────────
reset()
with patch.object(ts.requests, "get",
                  side_effect=http_error(429)), \
     patch.object(ts, "_get_openai_client", return_value=None), no_sleep():
    check("no fallback client: returns None",
          ts.translate_chunk("hello", "ar") is None)

# ── 8. Empty text -> None, no network ───────────────────────────────────────
reset()
with patch.object(ts.requests, "get") as g, \
     patch.object(ts, "_get_openai_client", return_value=fake_openai()):
    check("empty text: None", ts.translate_chunk("   ", "ar") is None)
    check("empty text: no Google call", g.call_count == 0)

# ── 9. Fallback success is cached (no double billing) ──────────────────────
reset()
oa = fake_openai("مخزن")
with patch.object(ts.requests, "get",
                  side_effect=http_error(429)), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    ts.translate_chunk("hello", "ar")
    ts.translate_chunk("hello", "ar")
check("fallback result cached: OpenAI called once",
      oa.responses.create.call_count == 1)

# ── 10. Non-429 HTTP error (400) -> fallback, breaker NOT tripped ──────────
reset()
oa = fake_openai("ب")
with patch.object(ts.requests, "get",
                  side_effect=http_error(400)), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    check("400: falls back to OpenAI",
          ts.translate_chunk("hello", "ar") == "ب")
check("400: breaker not tripped", ts._gtx_breaker["until"] == 0.0)

# ── 11. 500s: retried per chunk, fallback serves, no breaker trip ───────────
reset()
oa = fake_openai("ب")
with patch.object(ts.requests, "get",
                  side_effect=http_error(500)) as g, \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    check("500 wave: fallback serves",
          ts.translate_chunk("hello", "ar") == "ب")
    check("500 wave: retried 3 times", g.call_count == 3)
check("500 wave: 429-breaker not tripped", ts._gtx_breaker["until"] == 0.0)

# ── 12. translate_text: mixed chunks still join ─────────────────────────────
reset()
calls = {"n": 0}


def mixed_get(*a, **k):
    calls["n"] += 1
    if calls["n"] == 1:
        return gtx_ok("أولا")
    raise http_error(429)


oa = fake_openai("ثانيا")
long_text = "one " * 300  # >1000 chars -> 2 chunks: google ok, then 429s
with patch.object(ts.requests, "get", side_effect=mixed_get), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    out = ts.translate_text(long_text, "ar")
check("translate_text: joins google + fallback chunks",
      out is not None and "أولا" in out and "ثانيا" in out)

# ── 13. Budget exhausted: fallback disabled, client untouched ─────────────
import json as _json
import tempfile as _tempfile
reset()
_ts_tmp = _tempfile.mktemp(suffix=".json")
with open(_ts_tmp, "w") as f:
    _json.dump({"month": ts._budget_month(), "estimated_usd": 5.00}, f)
oa = fake_openai("x")
ts._budget_tripped_logged = False
with patch.object(ts, "_BUDGET_PATH", _ts_tmp), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    check("budget exhausted: fallback returns None",
          ts._openai_translate("hello", "ar") is None)
    check("budget exhausted: OpenAI not called",
          oa.responses.create.call_count == 0)
os.remove(_ts_tmp)

# ── 14. Successful fallback records estimated spend ────────────────────────
reset()
_ts_tmp2 = _tempfile.mktemp(suffix=".json")
oa = fake_openai("ترجمة")
with patch.object(ts, "_BUDGET_PATH", _ts_tmp2), \
     patch.object(ts, "_get_openai_client", return_value=oa), no_sleep():
    out = ts._openai_translate("hello world", "ar")
check("budget: translation served", out == "ترجمة")
with open(_ts_tmp2) as f:
    _st = _json.load(f)
check("budget: spend recorded", _st["estimated_usd"] > 0)
check("budget: short text costs a fraction of a cent",
      _st["estimated_usd"] < 0.01)
os.remove(_ts_tmp2)

# ── 15. Month rollover resets the budget ───────────────────────────────────
reset()
_ts_tmp3 = _tempfile.mktemp(suffix=".json")
with open(_ts_tmp3, "w") as f:
    _json.dump({"month": "1999-01", "estimated_usd": 5.00}, f)
with patch.object(ts, "_BUDGET_PATH", _ts_tmp3):
    check("budget: new month re-allows fallback", ts._budget_allow() is True)
os.remove(_ts_tmp3)

# ── 16. Boundary-aware chunking (round-68c) ───────────────────────────────
# Regression shape from the wild: the old hard 1000-char slice cut
# "Back that shit up" into "Back that shit u" / "p", and the orphan "p"
# leaked into the translated output.  Chunks must break only at lines.
reset()
_body = "a\n" * 499 + "Back that shit up\n" + "b\n" * 600  # >1000 chars
_chunks = ts.split_lyrics_chunks(_body)
check("chunker: 'Back that shit up' survives intact in one chunk",
      any("Back that shit up" in c for c in _chunks))
check("chunker: every chunk boundary falls on a line break",
      _chunk_boundaries_on_lines(_body, _chunks))
check("chunker: every chunk <= 1000 chars",
      all(len(c) <= 1000 for c in _chunks))
check("chunker: join reproduces the input exactly",
      "\n".join(_chunks) == _body)
check("chunker: every original line stays whole in one chunk",
      all(any(ln in c.split("\n") for c in _chunks)
          for ln in _body.split("\n")))
check("chunker: short text stays one chunk",
      ts.split_lyrics_chunks("hello\nworld") == ["hello\nworld"])
check("chunker: empty text -> no chunks",
      ts.split_lyrics_chunks("") == [])
# Pathological single line >1000 chars: hard-split, never crash
_long_line = "z" * 2500
_ll_chunks = ts.split_lyrics_chunks(_long_line)
check("chunker: overlong single line is split without crashing",
      len(_ll_chunks) == 3 and all(len(c) <= 1000 for c in _ll_chunks))
check("chunker: overlong line round-trips",
      "".join(_ll_chunks) == _long_line)

print(f"\nround68: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
