"""Round 64: share-card upload retry. Run: ../venv/bin/python test_round64.py

The 04:13 +03 share-card failure (TimeoutError on the final reply_photo)
had zero retry — one transient read timeout collapsed the whole request.
_send_with_retry (handlers.py) now retries transient upload failures
(TimedOut / NetworkError incl. Bad Gateway / RetryAfter) with bounded
attempts and short backoff, rewinding file payloads before each attempt.
"""
import io
import os
import sys
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram.error import TimedOut, NetworkError, RetryAfter, BadRequest

import handlers
from handlers import _send_with_retry, _SEND_ATTEMPTS, _RETRY_AFTER_CAP_S

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def run(fn, *args, **kwargs):
    """Call _send_with_retry with time.sleep stubbed; return (result, sleeps)."""
    sleeps = []
    with mock.patch.object(time, "sleep", side_effect=lambda s: sleeps.append(s)):
        try:
            return fn(*args, **kwargs), None, sleeps
        except Exception as e:
            return None, e, sleeps


class FlakySend:
    """Fails `fails` times with `exc`, then returns 'OK'. Records the file
    position seen at each call to prove payloads are rewound."""

    def __init__(self, fails, exc):
        self.fails = fails
        self.exc = exc
        self.calls = 0
        self.positions = []

    def __call__(self, photo=None, **kwargs):
        self.calls += 1
        self.positions.append(photo.tell())
        photo.read(10)  # simulate urllib3 consuming part of the stream
        if self.calls <= self.fails:
            raise self.exc
        return "OK"


# 1. Transient timeouts: fail twice with TimedOut, then succeed.
flaky = FlakySend(2, TimedOut())
res, err, sleeps = run(_send_with_retry, flaky, photo=io.BytesIO(b"x" * 100),
                       label="t1")
check("timed-out-twice recovers", (res, err), ("OK", None))
check("timed-out-twice attempts", flaky.calls, 3)
check("backoff sleeps between attempts", len(sleeps), 2)
check("payload rewound before every attempt", flaky.positions, [0, 0, 0])

# 2. Persistent network failure: NetworkError every time -> raises after N tries.
flaky = FlakySend(99, NetworkError("connection reset by peer"))
res, err, sleeps = run(_send_with_retry, flaky, photo=io.BytesIO(b"x" * 100),
                       label="t2")
check("persistent failure raises NetworkError", isinstance(err, NetworkError), True)
check("bounded attempts", flaky.calls, _SEND_ATTEMPTS)
check("sleeps = attempts - 1", len(sleeps), _SEND_ATTEMPTS - 1)

# 3. Non-transient errors are NOT retried: BadRequest raises on first call.
flaky = FlakySend(99, BadRequest("wrong file identifier"))
res, err, sleeps = run(_send_with_retry, flaky, photo=io.BytesIO(b"x" * 100),
                       label="t3")
check("BadRequest raises immediately", isinstance(err, BadRequest), True)
check("BadRequest not retried", flaky.calls, 1)
check("no sleep for non-transient", sleeps, [])

# 4. Flood control: RetryAfter delay honored, then success.
flaky = FlakySend(1, RetryAfter(5))
res, err, sleeps = run(_send_with_retry, flaky, photo=io.BytesIO(b"x" * 100),
                       label="t4")
check("RetryAfter recovers", (res, err), ("OK", None))
check("RetryAfter delay honored", sleeps, [5.0])

# 5. Absurd RetryAfter is capped.
flaky = FlakySend(1, RetryAfter(3600))
res, err, sleeps = run(_send_with_retry, flaky, photo=io.BytesIO(b"x" * 100),
                       label="t5")
check("absurd RetryAfter recovers", (res, err), ("OK", None))
check("RetryAfter capped", sleeps, [float(_RETRY_AFTER_CAP_S)])

# 6. Non-file kwargs don't break the rewind pass (caption str has no seek).
calls = {"n": 0}


def plain_send(photo=None, caption=None):
    calls["n"] += 1
    return (photo, caption)


res, err, _ = run(_send_with_retry, plain_send, photo=b"raw-bytes",
                  caption="plain caption", label="t6")
check("non-seekable payload passes through", (res, err),
      ((b"raw-bytes", "plain caption"), None))
check("success path single call", calls["n"], 1)

# 7. Both share-card upload sites actually use the retry wrapper.
import inspect
src = inspect.getsource(handlers.share_card_command)
check("cache-hit upload wrapped", "_send_with_retry" in src, True)
check("both reply_photo sites wrapped",
      src.count("_send_with_retry") >= 2, True)
check("success-path log line unchanged",
      "[sharecard] served card for" in src, True)
check("user-facing failure text unchanged",
      "Couldn't create the share card" in src, True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
