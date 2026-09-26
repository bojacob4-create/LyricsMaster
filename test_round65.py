"""Round 65: this machine is production — IS_PRODUCTION flip. Run: ../venv/bin/python test_round65.py

The bot ran with IS_PRODUCTION=False (Replit-era dev semantics) on the
machine that is now its production home. In dev mode a getUpdates Conflict
makes the live bot yield polling to the intruder and stay dark up to 2h.
The flag now reads PRODUCTION=1 (with REPLIT_DEPLOYMENT=1 as fallback),
and the owner-DM wording is mode-aware (it previously always claimed the
bot had paused, which is only true in dev mode).
"""
import os
import subprocess
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}")


REPO = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(os.path.dirname(REPO), "venv", "bin", "python")


def _flag_with(extra_env):
    """IS_PRODUCTION as seen by a fresh bot.py import under extra_env."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PRODUCTION", "REPLIT_DEPLOYMENT")}
    env.update(extra_env)
    script = ("import sys; sys.path.insert(0, %r); "
              "import bot; print(bot.IS_PRODUCTION)" % REPO)
    out = subprocess.run([VENV_PY, "-c", script], capture_output=True,
                         text=True, env=env, cwd=REPO, timeout=60)
    if out.returncode != 0:
        print("subprocess stderr:", out.stderr[-500:])
    return out.returncode == 0 and out.stdout.strip() == "True"


# ── 1. Flag semantics ─────────────────────────────────────────────────────
check("PRODUCTION=1 -> IS_PRODUCTION True", _flag_with({"PRODUCTION": "1"}))
check("REPLIT_DEPLOYMENT=1 -> IS_PRODUCTION True",
      _flag_with({"REPLIT_DEPLOYMENT": "1"}))
check("neither set -> IS_PRODUCTION False", not _flag_with({}))
check("PRODUCTION=0 -> IS_PRODUCTION False",
      not _flag_with({"PRODUCTION": "0"}))

# ── 2. Mode-aware owner DM text ───────────────────────────────────────────
import bot as botmod

with mock.patch.object(botmod, "IS_PRODUCTION", True):
    prod_text = botmod._conflict_alert_text()
with mock.patch.object(botmod, "IS_PRODUCTION", False):
    dev_text = botmod._conflict_alert_text()

check("prod DM says staying online", "staying online" in prod_text)
check("prod DM says fighting over messages",
      "fighting over your messages" in prod_text)
check("prod DM does not claim paused", "paused" not in prod_text)
check("dev DM says paused", "paused" in dev_text)
check("dev DM says resume on my own", "resume on my own" in dev_text)
check("both DM variants mention token rotation",
      "token may need rotating" in prod_text
      and "token may need rotating" in dev_text)

# ── 3. Conflict arbitration: production holds ground, dev yields ──────────
def _conflict_worker(prod_mode):
    w = botmod.TelegramBotWorker.__new__(botmod.TelegramBotWorker)
    w._last_conflict_at = 0
    ctx = mock.Mock()
    ctx.error = Exception("Conflict: terminated by other getUpdates request; "
                          "make sure that only one bot instance is running")
    with mock.patch.object(botmod, "IS_PRODUCTION", prod_mode):
        with mock.patch.object(botmod.TelegramBotWorker, "_stop_polling") as sp, \
             mock.patch.object(botmod.TelegramBotWorker,
                               "_maybe_alert_owner_conflict") as alert:
            botmod.TelegramBotWorker.error_handler(w, None, ctx)
    return sp, alert


sp_prod, alert_prod = _conflict_worker(True)
check("production conflict: does NOT stop polling",
      sp_prod.call_count == 0)
check("production conflict: still alerts owner",
      alert_prod.call_count == 1)

sp_dev, alert_dev = _conflict_worker(False)
check("dev conflict: stops polling (yields)",
      sp_dev.call_count == 1)
check("dev conflict: still alerts owner",
      alert_dev.call_count == 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
