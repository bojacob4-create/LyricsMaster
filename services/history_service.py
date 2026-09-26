"""Per-user song view history — powers the /history command.

Every song dashboard the user opens is recorded here (persistent JSON,
survives restarts). Re-viewing a song bumps it to the top instead of
duplicating it; the list is capped at the 30 most recent views.

Storage is an untracked runtime file (like the translate breaker/budget
state): ``.history.json`` next to the repo root, overridable via
``LYRICS_HISTORY_PATH``. Never imported by tests against the production
path — test files must patch ``_HISTORY_PATH`` to a temp file.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_HISTORY_PATH = os.environ.get(
    "LYRICS_HISTORY_PATH", os.path.join(_BASE_DIR, ".history.json"))
_MAX_ENTRIES = 30

_lock = threading.RLock()


def _norm_key(artist: str, title: str) -> str:
    return f"{(artist or '').strip().lower()}|{(title or '').strip().lower()}"


def _load() -> Dict:
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: Dict) -> None:
    try:
        tmp = _HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _HISTORY_PATH)
    except Exception as e:
        logger.warning(f"[history] save failed: {e}")


def record_view(user_id, artist: str, title: str) -> None:
    """Record one song dashboard view. Never raises."""
    try:
        artist = (artist or "").strip()
        title = (title or "").strip()
        if not artist or not title:
            return
        key = _norm_key(artist, title)
        with _lock:
            data = _load()
            entries = data.get(str(user_id)) or []
            # Drop any older entry for the same song (recency bump).
            entries = [e for e in entries
                       if _norm_key(e.get("artist"), e.get("title")) != key]
            entries.insert(0, {"artist": artist, "title": title,
                               "ts": time.time()})
            data[str(user_id)] = entries[:_MAX_ENTRIES]
            _save(data)
    except Exception as e:
        logger.warning(f"[history] record_view failed: {e}")


def get_history(user_id) -> List[Dict]:
    """Most-recent-first [{artist, title, ts}]. Never raises."""
    try:
        with _lock:
            entries = (_load().get(str(user_id)) or [])
        out = []
        for e in entries:
            if e.get("artist") and e.get("title"):
                out.append({"artist": e["artist"], "title": e["title"],
                            "ts": float(e.get("ts") or 0)})
        return out
    except Exception as e:
        logger.warning(f"[history] get_history failed: {e}")
        return []


def clear_history(user_id) -> int:
    """Clear one user's history. Returns the number of entries removed."""
    try:
        with _lock:
            data = _load()
            removed = len(data.get(str(user_id)) or [])
            data.pop(str(user_id), None)
            _save(data)
            return removed
    except Exception as e:
        logger.warning(f"[history] clear_history failed: {e}")
        return 0


def format_when(ts: float, now: float = None) -> str:
    """Relative label: 'today 13:32', 'yesterday 18:05', or '26 Sep'."""
    try:
        now = now if now is not None else time.time()
        day = datetime.fromtimestamp(ts).date()
        today = datetime.fromtimestamp(now).date()
        delta = (today - day).days
        hm = datetime.fromtimestamp(ts).strftime("%H:%M")
        if delta <= 0:
            return f"today {hm}"
        if delta == 1:
            return f"yesterday {hm}"
        return datetime.fromtimestamp(ts).strftime("%d %b")
    except Exception:
        return ""
