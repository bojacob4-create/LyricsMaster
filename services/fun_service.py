"""Fun social features for the Lyrics Master Telegram bot.

Covers: 1v1 quiz duels, a daily challenge with streaks, an emoji song-guessing
game, per-user music taste stats, and achievement badges.

Resilience design ("no limitations" build):
  * Everything runs primarily on unlimited LOCAL sources: curated pools,
    local JSON files, and local computation.
  * Rate-limited / quota'd APIs (OpenAI, Last.fm, lyrics providers) are
    OPTIONAL enhancement only. They are always wrapped in try/except with a
    graceful local fallback, plus aggressive caching so a repeated request
    never re-hits a failing API:
      - Quiz questions (which need lyrics providers) go through
        _get_question_cached(): up to 3 live attempts, every success is banked
        in a runtime cache file (QUIZ_CACHE_PATH, capped at ~200 questions),
        and on total failure a random cached question is served instead.
        An in-memory session set also prevents re-requesting the same song
        twice in one process lifetime.
      - Emoji puzzles: curated EMOJI_PUZZLES (>= 20 hand-made) is the primary
        source. OpenAI is enhancement-only; generated puzzles are cached
        in-memory so repeats never re-call, and a short cooldown after a
        failure means we fail over to curated puzzles instantly instead of
        waiting out a 10s timeout on every call.
  * Module import performs ZERO network I/O (OpenAI client is lazy-loaded
    inside the one function that uses it).
  * All JSON persistence follows the quiz_service.py pattern: read/write
    helpers that never raise, files live next to the module (repo root, like
    quiz_scores.json) and must never be committed to git.
"""

import json
import logging
import os
import random
import re
import string
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Local, network-free imports from the quiz service. quiz_service itself does
# no network I/O at import time (lyrics fetching is lazy inside functions).
from services.quiz_service import get_quiz_question, get_quiz_songs, _normalize


# ── Runtime JSON files (next to the module; NEVER commit these) ────────────
# Tests may monkeypatch these constants — always read the module global.
_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DUELS_PATH = os.path.join(_BASE_DIR, "fun_duels.json")
DAILY_PATH = os.path.join(_BASE_DIR, "fun_daily.json")
STATS_PATH = os.path.join(_BASE_DIR, "fun_stats.json")
BADGES_PATH = os.path.join(_BASE_DIR, "fun_badges.json")
QUIZ_CACHE_PATH = os.path.join(_BASE_DIR, "fun_quiz_cache.json")

_QUIZ_CACHE_MAX = 200      # max questions banked in the runtime cache file
_DUEL_QUESTION_COUNT = 5   # questions per duel
_AI_FAIL_COOLDOWN = 300    # seconds to skip OpenAI after a failure


# ── Never-raise JSON persistence (same pattern as quiz_service.py) ─────────

def _load_json(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: str, data: Dict) -> None:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"Could not save {path}: {e}")


# ── Resilient question pipeline ────────────────────────────────────────────
# Lyrics providers are rate-limitable, so every generated question is banked
# in a runtime cache file. If the providers are down, duels/daily fall back
# to cached questions and the game still works.

_QUIZ_CACHE_MEM: Dict[str, List[Dict]] = {}  # path -> cached questions
_SESSION_USED_SONGS = set()  # (artist_norm, song_norm) served this session


def _song_key(artist, song):
    return (_normalize(str(artist or "")), _normalize(str(song or "")))


def _load_quiz_cache() -> List[Dict]:
    """Lazy in-memory view of the runtime question cache file."""
    path = QUIZ_CACHE_PATH
    if path in _QUIZ_CACHE_MEM:
        return _QUIZ_CACHE_MEM[path]
    data = _load_json(path)
    cached = data.get("questions", [])
    if not isinstance(cached, list):
        cached = []
    _QUIZ_CACHE_MEM[path] = cached
    return cached


def _bank_question(question: Dict) -> None:
    """Append a successfully built question to the runtime cache (capped)."""
    try:
        if not isinstance(question, dict):
            return
        if not question.get("artist") or not question.get("song"):
            return
        cached = _load_quiz_cache()
        key = _song_key(question.get("artist"), question.get("song"))
        if any(_song_key(c.get("artist"), c.get("song")) == key
               for c in cached if isinstance(c, dict)):
            return  # already banked
        cached.append(dict(question))
        if len(cached) > _QUIZ_CACHE_MAX:
            del cached[:-_QUIZ_CACHE_MAX]  # drop oldest, keep newest ~200
        _save_json(QUIZ_CACHE_PATH, {"questions": cached})
    except Exception:
        pass  # cache banking must never break the game


def _get_question_cached(exclude: List[Dict] = None) -> Optional[Dict]:
    """Build one quiz question, resilient to lyrics-API outages.

    Tries get_quiz_question up to 3 times; each success is banked in the
    runtime cache. On total failure, returns a random cached question not
    already excluded (or None when the cache is empty).
    """
    try:
        exclude = list(exclude or [])
        used = {_song_key(s.get("artist"), s.get("song"))
                for s in exclude if isinstance(s, dict)}
        used |= _SESSION_USED_SONGS

        for _ in range(3):
            try:
                # Reference the module global so tests can monkeypatch it.
                q = get_quiz_question(exclude_songs=exclude)
            except Exception:
                q = None
            if (isinstance(q, dict) and q.get("artist") and q.get("song")
                    and q.get("options") is not None):
                key = _song_key(q.get("artist"), q.get("song"))
                if key in used:
                    # Already picked this session — exclude and try another.
                    exclude = exclude + [{"artist": q.get("artist"),
                                          "song": q.get("song")}]
                    used.add(key)
                    continue
                _SESSION_USED_SONGS.add(key)
                _bank_question(q)
                return q

        # Degraded mode: serve a random cached question we haven't used yet.
        candidates = [c for c in _load_quiz_cache()
                      if isinstance(c, dict)
                      and _song_key(c.get("artist"), c.get("song")) not in used]
        if candidates:
            pick = random.choice(candidates)
            _SESSION_USED_SONGS.add(
                _song_key(pick.get("artist"), pick.get("song")))
            return dict(pick)
        return None
    except Exception as e:
        logger.warning(f"_get_question_cached failed: {e}")
        return None


def _build_question_list(n: int) -> List[Dict]:
    """Assemble up to n questions via the resilient pipeline.

    Returns whatever could be assembled — possibly fewer than n (or empty)
    when providers are down and the cache is exhausted. Handlers must cope
    with short games.
    """
    questions, exclude = [], []
    for _ in range(max(0, n)):
        q = _get_question_cached(exclude)
        if q:
            questions.append(q)
            exclude.append({"artist": q.get("artist"), "song": q.get("song")})
    return questions


# ── Duel ───────────────────────────────────────────────────────────────────

# Duels expire 24h after creation (round 6 QA): old codes stayed joinable
# forever and fun_duels.json grew unbounded.
DUEL_TTL_SECONDS = 24 * 3600


def _prune_expired_duels(duels: Dict) -> bool:
    """Remove duels older than DUEL_TTL_SECONDS. Returns True if pruned."""
    now = time.time()
    expired = [code for code, d in duels.items()
               if isinstance(d, dict)
               and now - d.get("created", 0) > DUEL_TTL_SECONDS]
    for code in expired:
        duels.pop(code, None)
    if expired:
        logger.info(f"Pruned {len(expired)} expired duel(s)")
    return bool(expired)


def make_duel_code() -> str:
    """Random 6-char uppercase alphanumeric duel code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=6))


def create_duel(creator_id: int, creator_name: str,
                questions: List[Dict] = None) -> Dict:
    """Create a duel. Questions are injected or generated (resilient).

    Returns the duel dict; on unexpected failure returns {} (never raises).
    """
    try:
        duels = _load_json(DUELS_PATH)
        if _prune_expired_duels(duels):
            _save_json(DUELS_PATH, duels)
        code = make_duel_code()
        for _ in range(10):  # ensure uniqueness against existing duels
            if code not in duels:
                break
            code = make_duel_code()

        if questions is None:
            # Resilient pipeline: live build with cached fallback.
            questions = _build_question_list(_DUEL_QUESTION_COUNT)
        else:
            questions = list(questions)
            for q in questions:
                _bank_question(q)  # bank injected questions too

        duel = {
            "code": code,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "opponent_id": None,
            "opponent_name": None,
            "questions": questions,
            "answers": {str(creator_id): []},
            "created": time.time(),
        }
        duels[code] = duel
        _save_json(DUELS_PATH, duels)
        return duel
    except Exception as e:
        logger.warning(f"create_duel failed: {e}")
        return {}


def join_duel(code: str, user_id: int, user_name: str) -> Optional[Dict]:
    """Join a duel by code (case-insensitive, whitespace trimmed).

    Returns the duel, or None if the code is unknown / already taken by
    someone else. Never raises.
    """
    try:
        duels = _load_json(DUELS_PATH)
        if _prune_expired_duels(duels):
            _save_json(DUELS_PATH, duels)
        key = str(code or "").strip().upper()
        duel = duels.get(key)
        if not isinstance(duel, dict):
            return None
        opp = duel.get("opponent_id")
        if opp is not None and opp != user_id:
            return None  # duel already has a different opponent
        duel["opponent_id"] = user_id
        duel["opponent_name"] = user_name
        answers = duel.get("answers")
        if not isinstance(answers, dict):
            answers = {}
            duel["answers"] = answers
        answers.setdefault(str(user_id), [])
        _save_json(DUELS_PATH, duels)
        return dict(duel)
    except Exception as e:
        logger.warning(f"join_duel failed: {e}")
        return None


def get_duel(code: str) -> Optional[Dict]:
    try:
        duels = _load_json(DUELS_PATH)
        duel = duels.get(str(code or "").strip().upper())
        return dict(duel) if isinstance(duel, dict) else None
    except Exception:
        return None


def get_duel_questions(code: str) -> List[Dict]:
    """The shared question list for a duel (copies, may be short)."""
    try:
        duel = get_duel(code)
        if not duel:
            return []
        return [dict(q) for q in duel.get("questions", [])
                if isinstance(q, dict)]
    except Exception:
        return []


def record_duel_answer(code: str, user_id: int, correct: bool) -> None:
    """Append one answer (True/False) for a player. Never raises."""
    try:
        duels = _load_json(DUELS_PATH)
        key = str(code or "").strip().upper()
        duel = duels.get(key)
        if not isinstance(duel, dict):
            return
        answers = duel.get("answers")
        if not isinstance(answers, dict):
            answers = {}
            duel["answers"] = answers
        mine = answers.setdefault(str(user_id), [])
        nq = len(duel.get("questions", []))
        if len(mine) < nq:  # ignore extra answers past the last question
            mine.append(bool(correct))
            _save_json(DUELS_PATH, duels)
    except Exception as e:
        logger.warning(f"record_duel_answer failed: {e}")


def duel_standings(code: str) -> Dict:
    """Scores/progress for both players.

    Keys are str(user_id). 'winner' is a uid, 'tie', or None — a winner is
    only declared once BOTH players have answered every question.
    """
    empty = {"names": {}, "scores": {}, "answered": {},
             "finished": {}, "winner": None}
    try:
        duel = get_duel(code)
        if not duel:
            return empty
        names = {str(duel.get("creator_id")): duel.get("creator_name")}
        if duel.get("opponent_id") is not None:
            names[str(duel.get("opponent_id"))] = duel.get("opponent_name")
        answers = duel.get("answers") or {}
        nq = len(duel.get("questions", []))

        scores = {uid: sum(1 for a in answers.get(uid, []) if a)
                  for uid in names}
        answered = {uid: min(len(answers.get(uid, [])), nq) for uid in names}
        finished = {uid: nq > 0 and answered[uid] >= nq for uid in names}

        winner = None
        if nq > 0 and len(names) == 2 and all(finished.values()):
            uids = list(names)
            if scores[uids[0]] > scores[uids[1]]:
                winner = uids[0]
            elif scores[uids[1]] > scores[uids[0]]:
                winner = uids[1]
            else:
                winner = "tie"
        return {"names": names, "scores": scores, "answered": answered,
                "finished": finished, "winner": winner}
    except Exception as e:
        logger.warning(f"duel_standings failed: {e}")
        return empty


def delete_duel(code: str) -> None:
    try:
        duels = _load_json(DUELS_PATH)
        if duels.pop(str(code or "").strip().upper(), None) is not None:
            _save_json(DUELS_PATH, duels)
    except Exception as e:
        logger.warning(f"delete_duel failed: {e}")


# ── Daily challenge ────────────────────────────────────────────────────────

def _today_str(today: Optional[str]) -> str:
    return today or date.today().isoformat()


def get_daily_status(user_id: int, today: str = None) -> Dict:
    """{'can_play': bool, 'streak': int, 'best_streak': int}.

    can_play is False once the user has STARTED today's game — starting
    counts as playing (round 39: previously only a finished game was
    recorded, so /daily -> /daily or /daily -> /cancel -> /daily silently
    re-rolled the questions).
    """
    try:
        today = _today_str(today)
        data = _load_json(DAILY_PATH)
        entry = data.get(str(user_id), {})
        if not isinstance(entry, dict):
            entry = {}
        return {
            "can_play": (entry.get("last_played") != today
                         and entry.get("last_started") != today),
            "streak": int(entry.get("streak", 0) or 0),
            "best_streak": int(entry.get("best_streak", 0) or 0),
        }
    except Exception:
        return {"can_play": True, "streak": 0, "best_streak": 0}


def mark_daily_started(user_id: int, today: str = None) -> None:
    """Record that today's daily game was started (round 39).

    Writes last_started without touching streak/best_streak/last_played —
    streaks are still computed only when the game is FINISHED via
    record_daily_play. Never raises.
    """
    try:
        today = _today_str(today)
        data = _load_json(DAILY_PATH)
        key = str(user_id)
        entry = data.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["last_started"] = today
        data[key] = entry
        _save_json(DAILY_PATH, data)
    except Exception as e:
        logger.warning(f"mark_daily_started failed: {e}")


def record_daily_play(user_id: int, score: int, total: int,
                      today: str = None) -> Dict:
    """Record a daily-challenge play.

    Streak +1 if yesterday was played, else resets to 1. Playing twice the
    same day returns the current values unchanged. Never raises.
    """
    try:
        today = _today_str(today)
        data = _load_json(DAILY_PATH)
        key = str(user_id)
        entry = data.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        last = entry.get("last_played")
        streak = int(entry.get("streak", 0) or 0)
        best = int(entry.get("best_streak", 0) or 0)

        if last == today:
            return {"streak": streak, "best_streak": best, "new_best": False}

        try:
            yesterday = (date.fromisoformat(today)
                         - timedelta(days=1)).isoformat()
        except Exception:
            yesterday = None
        streak = streak + 1 if last == yesterday else 1
        new_best = streak > best
        best = max(best, streak)

        data[key] = {"last_played": today, "streak": streak,
                     "best_streak": best}
        _save_json(DAILY_PATH, data)
        return {"streak": streak, "best_streak": best, "new_best": new_best}
    except Exception as e:
        logger.warning(f"record_daily_play failed: {e}")
        return {"streak": 0, "best_streak": 0, "new_best": False}


def make_daily_questions(n: int = 5, questions: List[Dict] = None) -> List[Dict]:
    """Daily-challenge questions: injected or built via the resilient pipeline.

    May return fewer than n when providers are down and the cache is
    exhausted — handlers must cope with short games. Never raises.
    """
    try:
        if questions is not None:
            qs = list(questions)
            for q in qs:
                _bank_question(q)
            return qs
        return _build_question_list(n)
    except Exception as e:
        logger.warning(f"make_daily_questions failed: {e}")
        return []


# ── Emoji game ─────────────────────────────────────────────────────────────

# Hand-made puzzles: the PRIMARY source (100% local, unlimited).
EMOJI_PUZZLES: List[Dict] = [
    {"emojis": "👑🎭", "artist": "Queen", "song": "Bohemian Rhapsody"},
    {"emojis": "📐💘", "artist": "Ed Sheeran", "song": "Shape of You"},
    {"emojis": "😎💡", "artist": "The Weeknd", "song": "Blinding Lights"},
    {"emojis": "👎💘", "artist": "Lady Gaga", "song": "Bad Romance"},
    {"emojis": "🎲🌊", "artist": "Adele", "song": "Rolling in the Deep"},
    {"emojis": "🏙️🕺", "artist": "Mark Ronson", "song": "Uptown Funk"},
    {"emojis": "🕺🐝❤️", "artist": "Bee Gees", "song": "Stayin' Alive"},
    {"emojis": "💃👑", "artist": "ABBA", "song": "Dancing Queen"},
    {"emojis": "🌍🦁", "artist": "Toto", "song": "Africa"},
    {"emojis": "👋👤", "artist": "a-ha", "song": "Take On Me"},
    {"emojis": "🚫🛑🙏", "artist": "Journey", "song": "Don't Stop Believin'"},
    {"emojis": "🍬👶🔫🌹", "artist": "Guns N' Roses",
     "song": "Sweet Child O' Mine"},
    {"emojis": "👃👧👻", "artist": "Nirvana",
     "song": "Smells Like Teen Spirit"},
    {"emojis": "🤔🧱", "artist": "Oasis", "song": "Wonderwall"},
    {"emojis": "☎️✨", "artist": "Drake", "song": "Hotline Bling"},
    {"emojis": "☂️☔", "artist": "Rihanna", "song": "Umbrella"},
    {"emojis": "😊🎶", "artist": "Pharrell Williams", "song": "Happy"},
    {"emojis": "💡🪩", "artist": "Sia", "song": "Chandelier"},
    {"emojis": "🔢⭐", "artist": "OneRepublic", "song": "Counting Stars"},
    {"emojis": "⏰👀", "artist": "Avicii", "song": "Wake Me Up"},
    {"emojis": "💐🌸", "artist": "Miley Cyrus", "song": "Flowers"},
    {"emojis": "☕⚡", "artist": "Sabrina Carpenter", "song": "Espresso"},
    {"emojis": "🎨🏙️🔴", "artist": "Doja Cat", "song": "Paint The Town Red"},
    {"emojis": "😌⬇️", "artist": "Rema", "song": "Calm Down"},
    {"emojis": "💨🏃", "artist": "Ayra Starr", "song": "Rush"},
    {"emojis": "🧛🩸", "artist": "Olivia Rodrigo", "song": "vampire"},
    {"emojis": "🍉🍬", "artist": "Harry Styles", "song": "Watermelon Sugar"},
    {"emojis": "⛪🙏", "artist": "Hozier", "song": "Take Me to Church"},
]

# OpenAI is enhancement-only: puzzles it invents are cached in-memory for the
# session so a repeat never re-calls the API.
_AI_PUZZLES: Dict[tuple, Dict] = {}
_AI_LAST_FAIL = 0.0

_EMOJI_SYS = """\
You invent emoji puzzles for song titles: a short emoji sequence that hints
at a famous song's title. Return ONLY a JSON object (no explanation, no extra
text) with exactly these keys:
{"emojis": "<2-6 emojis>", "artist": "<real artist name>", "song": "<real song title>"}
Make the emojis a clever visual pun on the song TITLE. Use the exact song and
artist I give you.
"""


def _invent_ai_puzzle(song_choice: Dict) -> Optional[Dict]:
    """Ask OpenAI for a fresh puzzle. Returns None on any failure (no key,
    timeout, bad JSON, empty fields) — the caller falls back to curated."""
    global _AI_LAST_FAIL
    try:
        # Graceful degradation: right after a failure, skip the API entirely
        # instead of burning a 10s timeout on every call.
        if time.time() - _AI_LAST_FAIL < _AI_FAIL_COOLDOWN:
            return None
        from services import nlp_router  # lazy: zero network at import
        client = nlp_router._get_client()
        if client is None:
            return None
        response = client.responses.create(
            model=nlp_router._MODEL,
            input=[
                {"role": "system", "content": _EMOJI_SYS},
                {"role": "user",
                 "content": ("Invent an emoji puzzle for the song "
                             f"\"{song_choice.get('song')}\" by "
                             f"{song_choice.get('artist')}.")},
            ],
            text={"format": {"type": "json_object"}},
            timeout=10,
        )
        data = json.loads(response.output_text)
        puzzle = {
            "emojis": str(data.get("emojis", "")).strip(),
            "artist": str(data.get("artist", "")).strip(),
            "song": str(data.get("song", "")).strip(),
        }
        if not puzzle["artist"] or not puzzle["song"] or not puzzle["emojis"]:
            return None
        return puzzle
    except Exception as e:
        _AI_LAST_FAIL = time.time()
        logger.debug(f"AI emoji puzzle failed, using curated: {e}")
        return None


def get_emoji_puzzle() -> Dict:
    """One emoji puzzle: AI-invented when possible, curated otherwise.

    Never raises; never needs the network to return something playable.
    """
    try:
        songs = get_quiz_songs()  # local, cached song pool
        if songs:
            choice = random.choice(songs)
            key = _song_key(choice.get("artist"), choice.get("song"))
            if key in _AI_PUZZLES:
                return dict(_AI_PUZZLES[key])  # repeat: no re-call
            ai_puzzle = _invent_ai_puzzle(choice)
            if ai_puzzle:
                _AI_PUZZLES[_song_key(ai_puzzle["artist"],
                                      ai_puzzle["song"])] = ai_puzzle
                return dict(ai_puzzle)
    except Exception as e:
        logger.debug(f"get_emoji_puzzle AI path failed: {e}")
    return dict(random.choice(EMOJI_PUZZLES))


def check_emoji_guess(puzzle: Dict, guess: str) -> bool:
    """Lenient guess check (same normalization as quiz_service).

    Accepts 'Artist - Song', just the song title, or a guess containing both
    the artist and the song title. Never raises.
    """
    try:
        if not isinstance(puzzle, dict):
            return False
        gn = _normalize(str(guess or ""))
        sn = _normalize(str(puzzle.get("song", "")))
        an = _normalize(str(puzzle.get("artist", "")))
        if not gn or not sn:
            return False
        if sn in gn:
            return True
        return bool(an) and an in gn and sn in gn
    except Exception:
        return False


# ── Music stats ────────────────────────────────────────────────────────────
# 100% local: counts interactions per user and derives a playful taste label.

# Display names for stored genre keys — plain .title() mangles these.
_GENRE_DISPLAY = {
    'rnb': 'R&B',
    'hiphop': 'Hip-Hop',
    'kpop': 'K-Pop',
}


def genre_display_name(genre) -> str:
    """Human-readable genre name for a stored lowercase genre key."""
    g = (genre or '').strip().lower()
    return _GENRE_DISPLAY.get(g, g.title())


def _norm_song_key(artist, title) -> str:
    """Normalized 'artist — title' key so re-served songs dedupe. '' if empty."""
    a = re.sub(r'\s+', ' ', (artist or '').strip().lower())
    t = re.sub(r'\s+', ' ', (title or '').strip().lower())
    return f'{a} — {t}' if (a or t) else ''


def log_interaction(user_id: int, kind: str, genre: str = None,
                    correct: bool = None, songs=None) -> None:
    """Log one interaction.

    kinds: 'random', 'recommend', 'song', 'quiz_start', 'quiz_correct',
    'quiz_wrong', 'duel', 'daily', 'emoji'. songs: optional iterable of
    (artist, title) pairs the bot served — each counts once toward the
    per-user distinct "songs explored" set. Never raises.
    """
    try:
        data = _load_json(STATS_PATH)
        key = str(user_id)
        entry = data.get(key) or {}
        genres = entry.get("genres") or {}
        kinds = entry.get("kinds") or {}
        if genre:
            g = str(genre).strip().lower()
            if g:
                genres[g] = genres.get(g, 0) + 1
        kinds[str(kind)] = kinds.get(str(kind), 0) + 1
        quiz_correct = int(entry.get("quiz_correct", 0) or 0)
        if kind == "quiz_correct":
            quiz_correct += 1
        song_map = entry.get("songs") or {}
        if not isinstance(song_map, dict):
            song_map = {}
        if songs:
            for _a, _t in songs:
                _k = _norm_song_key(_a, _t)
                if _k:
                    song_map[_k] = song_map.get(_k, 0) + 1
        total = int(entry.get("total", 0) or 0) + 1
        data[key] = {"genres": genres, "kinds": kinds,
                     "quiz_correct": quiz_correct, "total": total,
                     "songs": song_map}
        _save_json(STATS_PATH, data)
    except Exception as e:
        logger.warning(f"log_interaction failed: {e}")


def _taste_label(top: List[tuple], total: int, kinds=None) -> str:
    kinds = kinds or {}
    if total == 0 or not top:
        return "🌱 New listener — your taste profile is growing!"
    genre, pct = top[0]
    if genre == "afrobeats" and pct >= 60:
        return "🌍 Afrobeats explorer"
    # A balanced top two is a blend, not a single-genre identity.
    if len(top) >= 2:
        genre2, pct2 = top[1]
        if pct2 >= 20 and (pct - pct2) <= 10:
            return (f"🎧 {genre_display_name(genre)} × "
                    f"{genre_display_name(genre2)} blend")
    if pct >= 40:
        return f"🎧 {genre_display_name(genre)} lover"
    answered = int(kinds.get("quiz_correct", 0) or 0) + int(
        kinds.get("quiz_wrong", 0) or 0)
    if answered >= 10 and answered / max(total, 1) >= 0.5:
        return "🎯 Quiz shark"
    return "🎶 Musical omnivore"


def get_music_stats(user_id: int) -> Dict:
    """{'top': [(genre, pct_int), ...] (top 3, desc, pct of GENRE-TAGGED
    interactions so they sum to ~100), 'total': int (all interactions),
    'songs_explored': int (distinct songs served), 'quiz_correct': int,
    'quiz_answered': int, 'label': str}. Never raises."""
    try:
        data = _load_json(STATS_PATH)
        entry = data.get(str(user_id)) or {}
        if not isinstance(entry, dict):
            entry = {}
        total = int(entry.get("total", 0) or 0)
        quiz_correct = int(entry.get("quiz_correct", 0) or 0)
        kinds = entry.get("kinds") or {}
        quiz_wrong = int(kinds.get("quiz_wrong", 0) or 0)
        songs = entry.get("songs") or {}
        genres = entry.get("genres") or {}
        top = []
        genre_total = sum(genres.values())
        if genre_total > 0:
            ranked = sorted(genres.items(), key=lambda kv: kv[1],
                            reverse=True)[:3]
            top = [(g, int(round(c / genre_total * 100))) for g, c in ranked]
        return {"top": top, "total": total,
                "songs_explored": len(songs) if isinstance(songs, dict) else 0,
                "quiz_correct": quiz_correct,
                "quiz_answered": quiz_correct + quiz_wrong,
                "label": _taste_label(top, total, kinds)}
    except Exception as e:
        logger.warning(f"get_music_stats failed: {e}")
        return {"top": [], "total": 0, "songs_explored": 0,
                "quiz_correct": 0, "quiz_answered": 0,
                "label": "🌱 New listener — your taste profile is growing!"}


# ── Badges ─────────────────────────────────────────────────────────────────
# 100% local: awarded from stats/daily state, persisted per user.

BADGES: Dict[str, Dict] = {
    "first_quiz": {"emoji": "🎮", "name": "First Steps",
                   "desc": "Played your first quiz"},
    "quiz_whiz": {"emoji": "🏆", "name": "Quiz Whiz",
                  "desc": "10 correct quiz answers"},
    "streak_7": {"emoji": "🔥", "name": "On Fire",
                 "desc": "7-day daily streak"},
    "explorer": {"emoji": "🗺️", "name": "Explorer",
                 "desc": "Discovered 50 songs"},
    "duel_champ": {"emoji": "⚔️", "name": "Duel Champion",
                   "desc": "Won a duel"},
    "lucky": {"emoji": "🎲", "name": "Lucky Roll",
              "desc": "25 random picks"},
}


def award_badge(user_id: int, badge_id: str) -> bool:
    """Award a badge. True if newly awarded, False if already had (or the id
    is unknown). Never raises."""
    try:
        if badge_id not in BADGES:
            return False
        store = _load_json(BADGES_PATH)
        key = str(user_id)
        earned = store.get(key) or []
        if not isinstance(earned, list):
            earned = []
        if badge_id in earned:
            return False
        earned.append(badge_id)
        store[key] = earned
        _save_json(BADGES_PATH, store)
        return True
    except Exception as e:
        logger.warning(f"award_badge failed: {e}")
        return False


def get_user_badges(user_id: int) -> Dict:
    """{'earned': [ids in BADGES order], 'locked': [ids]}. Never raises."""
    try:
        store = _load_json(BADGES_PATH)
        earned_set = set(store.get(str(user_id)) or [])
        earned = [b for b in BADGES if b in earned_set]
        locked = [b for b in BADGES if b not in earned_set]
        return {"earned": earned, "locked": locked}
    except Exception as e:
        logger.warning(f"get_user_badges failed: {e}")
        return {"earned": [], "locked": list(BADGES)}


def auto_award_from_stats(user_id: int) -> List[str]:
    """Award whatever the user's stats qualify for. Returns the list of
    NEWLY awarded badge ids (in check order). Never raises."""
    newly: List[str] = []
    try:
        stats = get_music_stats(user_id)
        daily = get_daily_status(user_id)
        raw = _load_json(STATS_PATH)
        entry = raw.get(str(user_id)) or {}
        kinds = entry.get("kinds") or {} if isinstance(entry, dict) else {}
        checks = [
            ("quiz_whiz", stats.get("quiz_correct", 0) >= 10),
            ("explorer", stats.get("total", 0) >= 50),
            ("lucky", int(kinds.get("random", 0) or 0) >= 25),
            ("streak_7", daily.get("best_streak", 0) >= 7),
        ]
        for badge_id, qualifies in checks:
            if qualifies and award_badge(user_id, badge_id):
                newly.append(badge_id)
        return newly
    except Exception as e:
        logger.warning(f"auto_award_from_stats failed: {e}")
        return newly
