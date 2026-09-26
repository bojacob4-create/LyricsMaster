"""Round 63: reliability hardening. Run: ../venv/bin/python test_round63.py

1. Reboot sentinel 3m -> 1m (cron schedule; verified via cron.view, not here).
2. Restart coordination: restart_bot.sh writes .last_restart on success and
   retries verification 3x before FAIL (no more FAIL on transient runners=2);
   sentinel + watchdog stand down when a restart happened <5 min ago.
3. Lyrics fail-fast: search_lyrics_with_fallback now has an overall deadline
   (default 15s) shared by every stage — a flap can no longer stack per-call
   timeouts into a 20s+ hang (seen 2026-09-26: 22.5s).
4. Conflict early-warning: a getUpdates Conflict DMs the owner (throttled),
   instead of the bot silently missing messages during a two-instance fight.
"""
import os
import sys
import time
import threading
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}")


import input_parser as ip

# ── Item 3: overall deadline ──────────────────────────────────────────────
# 3a. Already-expired deadline: no waiting, no hang.
t0 = time.time()
res = ip._parallel_search([("Tyla", "Water")], deadline=time.time() - 1)
check("3a expired deadline returns [None] fast",
      res == [None] and time.time() - t0 < 5)

# 3b. Deadline bites mid-chain: a stuck source can't hold the call.
stopper = threading.Event()


def _slow_fake(artist, song):
    stopper.wait(30)  # stuck downstream
    return None


orig = ip.search_song_info
ip.search_song_info = _slow_fake
try:
    t0 = time.time()
    out = ip.search_lyrics_with_fallback("Tyla - Water", timeout=1.5)
    dt = time.time() - t0
    check("3b stuck chain fails fast (~1.5s, not 30s+)",
          out == (None, None, None, "not_found") and dt < 8)
finally:
    stopper.set()
    ip.search_song_info = orig

# 3c. Normal path unaffected: instant hit still resolves via separator path.
ip.search_song_info = lambda a, s: ("Tyla", "Water", "x" * 100)  # noqa: E731
try:
    out = ip.search_lyrics_with_fallback("Tyla - Water", timeout=15)
    check("3c separator hit still works",
          out == ("Tyla", "Water", "x" * 100, "direct"))
    out = ip.search_lyrics_with_fallback("Tyla-Water", timeout=15)
    check("3c compact-dash hit still works", out[3] == "direct")
finally:
    ip.search_song_info = orig

# 3d. Generic-search path still works when the query has no dash.
calls = []


def _fake_generic(artist, song):
    calls.append((artist, song))
    if artist == "" and song == "some random song":
        return ("A", "S", "y" * 100)
    return None


ip.search_song_info = _fake_generic
try:
    out = ip.search_lyrics_with_fallback("some random song", timeout=15)
    check("3d generic search hit still works", out[3] == "search")
finally:
    ip.search_song_info = orig

# 3e. _best_of tolerates abandoned (None) pairs.
check("3e _best_of(None, None) is None", ip._best_of(None, None, "q") is None)

# ── Item 4: Conflict owner alert ───────────────────────────────────────────
import bot as botmod


def _make_worker(sent):
    w = botmod.TelegramBotWorker.__new__(botmod.TelegramBotWorker)

    class FakeBot:
        def send_message(self, chat_id=None, text=None, **kw):
            sent.append((chat_id, text))

    class FakeUpdater:
        bot = FakeBot()

    w.updater = FakeUpdater()
    return w


tmp = tempfile.NamedTemporaryFile(delete=False)
tmp.close()
orig_chat = botmod.OWNER_CHAT_ID
orig_file = botmod._CONFLICT_ALERT_FILE
botmod.OWNER_CHAT_ID = "169570389"
botmod._CONFLICT_ALERT_FILE = tmp.name
try:
    # 4a. First conflict -> DM sent, timestamp recorded.
    sent = []
    w = _make_worker(sent)
    w._maybe_alert_owner_conflict()
    check("4a conflict sends owner DM",
          len(sent) == 1 and sent[0][0] == 169570389
          and "Replit" in sent[0][1] and "token" in sent[0][1])

    # 4b. Second conflict within throttle -> no duplicate DM.
    w._maybe_alert_owner_conflict()
    check("4b alert throttled (no duplicate DM)", len(sent) == 1)

    # 4c. No owner configured -> silent no-op, never raises.
    botmod.OWNER_CHAT_ID = ""
    w2 = _make_worker(sent)
    w2._maybe_alert_owner_conflict()
    check("4c no OWNER_CHAT_ID is a silent no-op", len(sent) == 1)

    # 4d. Full error_handler wiring: Conflict error triggers the alert.
    from telegram.error import Conflict

    botmod.OWNER_CHAT_ID = "169570389"
    os.unlink(tmp.name)  # reset throttle so the DM fires
    sent4 = []
    w4 = _make_worker(sent4)

    class FakeCtx:
        error = Conflict("Conflict: terminated by other getUpdates request; "
                         "make sure that only one bot instance is running")

    # _stop_polling must not blow up with a stub updater.
    w4.error_handler(None, FakeCtx())
    check("4d error_handler routes Conflict to owner alert", len(sent4) == 1)
finally:
    botmod.OWNER_CHAT_ID = orig_chat
    botmod._CONFLICT_ALERT_FILE = orig_file
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)

# ── Item 2: restart coordination ──────────────────────────────────────────
# The exact predicate both cron bodies use (marker written by restart_bot.sh).
PRED = ('m="{m}"; '
        'if [ -f "$m" ] && [ $(($(date +%s) - $(cat "$m"))) -lt 300 ]; '
        'then echo SKIP; else echo GO; fi')


def _predicate(marker_path):
    r = subprocess.run(["bash", "-c", PRED.format(m=marker_path)],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


with tempfile.TemporaryDirectory() as d:
    m = os.path.join(d, ".last_restart")
    check("2a missing marker -> restart allowed", _predicate(m) == "GO")
    with open(m, "w") as f:
        f.write(str(int(time.time())))
    check("2b fresh marker -> restart skipped", _predicate(m) == "SKIP")
    with open(m, "w") as f:
        f.write(str(int(time.time()) - 400))
    check("2c stale marker (400s) -> restart allowed", _predicate(m) == "GO")

# restart_bot.sh contract: writes the marker on success, retries verification.
script = open(os.path.expanduser("~/workspace/lyrics-master/restart_bot.sh")).read()
check("2d script writes .last_restart on success",
      "date +%s > .last_restart" in script)
check("2e script retries verification (no single-shot FAIL)",
      "for attempt in 1 2 3" in script)

print(f"\n{ PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
