"""Round-24 tests: a stalled MP3 download child must actually die on terminate().

Found in the wild (2026-09-24 ~17:36 +03): the 45s stall-killer fired on a
stuck YouTube download, the log said "hard-killed", but the child was still
alive 2 minutes later holding ~80MB. Root cause: fork inherits bot.py's
SIGTERM handler, which catches the signal and shuts down gracefully WITHOUT
exiting — so terminate() never terminated anything.

Fix: the forked _child resets SIGTERM/SIGINT to SIG_DFL first thing, and the
parent escalates to p.kill() (SIGKILL, uncatchable) if the child somehow
survives terminate()+join(5).

These tests extract the REAL nested _child from the production module via
AST (no copies) and run it under a bot.py-like non-exiting SIGTERM handler.
"""
import ast
import inspect
import multiprocessing as mp
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import services.youtube_downloader_service as yds

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


def _real_child_fn(strip_reset=False):
    """Compile the actual nested _child from the production module source."""
    src = inspect.getsource(yds)
    seg = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "_child":
            seg = ast.get_source_segment(src, node)
            break
    assert seg, "could not find _child in production source"
    if strip_reset:
        seg = "\n".join(
            l for l in seg.splitlines()
            if "SIG_DFL" not in l and "import signal as _signal" not in l)
    ns = {"_download_url_to_mp3": lambda *a, **k: time.sleep(30)}
    exec(compile(ast.parse(seg), "<_child>", "exec"), ns)  # noqa: S102
    return ns["_child"]


def _bot_like_handler(signum, frame):
    # Mimics bot.py's signal_handler: graceful shutdown, NO exit.
    pass


def _run_child_and_terminate(child_fn):
    """Fork child_fn under a bot-like handler, terminate it, return liveness."""
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, _bot_like_handler)
    signal.signal(signal.SIGINT, _bot_like_handler)
    try:
        ctx = mp.get_context("fork")
        q = ctx.Queue()
        p = ctx.Process(target=child_fn, args=(q, "http://x", "pfx", "lbl"),
                        daemon=True)
        p.start()
        time.sleep(1.0)  # let the child reach the slow download
        assert p.is_alive(), "child should be busy downloading"
        p.terminate()
        p.join(5)
        alive = p.is_alive()
        if alive:
            p.kill()
            p.join(5)
        return alive
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


# ── 1. Fixed child dies on terminate() ─────────────────────────────────────
alive = _run_child_and_terminate(_real_child_fn())
check("fixed _child dies on terminate()", not alive,
      "child still alive after terminate()+join(5)")

# ── 2. Mutation check: without the reset, the child lingers ────────────────
alive_old = _run_child_and_terminate(_real_child_fn(strip_reset=True))
check("test detects the old bug (stripped reset lingers)", alive_old,
      "stripped child died — test would not catch a regression")

# ── 3. Parent escalates to SIGKILL ─────────────────────────────────────────
src = inspect.getsource(yds)
check("parent escalates terminate() -> kill()",
      "p.kill()" in src and "p.terminate()" in src)
check("production _child resets SIGTERM/SIGINT to default",
      src.count("SIG_DFL") >= 2)

print(f"\nround24: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
