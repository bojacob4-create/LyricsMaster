import logging
import json
import os
from typing import List, Dict, Optional, Tuple
import random
from functools import lru_cache

logger = logging.getLogger(__name__)

active_quizzes = {}

_SCORES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'quiz_scores.json')


# ── Song list: LIVE chart hits (no static pool) ─────────────────────────────
# Quiz questions are drawn from the current Apple Music Top 100 so the quiz
# stays current.  Charts are cached (~6h) inside live_charts and fall back to
# the last cached chart when the feed is down.

def get_quiz_songs() -> List[Dict]:
    """Current chart hits for quiz questions/distractors.  Never raises."""
    try:
        from services.live_charts import get_top_songs
        songs = get_top_songs(limit=100)
        if songs:
            return songs
    except Exception as e:
        logger.error(f"[QUIZ] Live chart unavailable: {e}")
    return []




# ── Persistent best scores ────────────────────────────────────────────────
# Writes go through utils.locked_json_update: the read-modify-write is held
# under a per-file lock and saved via tmp+rename, so concurrent quiz
# finishes can't clobber each other and a crash can't corrupt the file.

def _load_scores() -> Dict:
    try:
        with open(_SCORES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _record_game(user_id: int, quiz: Dict) -> None:
    """Persist personal bests (best score %, best streak, games played)."""
    try:
        from utils import locked_json_update

        def _update(scores: Dict) -> Dict:
            key = str(user_id)
            entry = scores.get(key, {"best_pct": 0, "best_streak": 0, "games": 0})
            total = quiz.get("total_questions", 0)
            pct = round(quiz.get("score", 0) / total * 100) if total else 0
            entry["best_pct"] = max(entry.get("best_pct", 0), pct)
            entry["best_streak"] = max(entry.get("best_streak", 0),
                                       quiz.get("best_streak", 0))
            entry["games"] = entry.get("games", 0) + 1
            scores[key] = entry
            return scores

        locked_json_update(_SCORES_PATH, _update, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Could not record quiz score: {e}")


def get_personal_best(user_id: int) -> Optional[Dict]:
    return _load_scores().get(str(user_id))


# ── Lyrics helpers (cached so repeat questions are instant) ───────────────

@lru_cache(maxsize=256)
def _get_lyrics_cached(artist: str, song: str) -> Optional[str]:
    from services.lyrics_service import get_song_lyrics
    try:
        return get_song_lyrics(artist, song)
    except Exception:
        return None


def _clean_lines(lyrics: str) -> List[str]:
    skip = ('chorus', 'verse', 'bridge', 'intro', 'outro', 'pre-chorus',
            'post-chorus', 'hook', '[', ']')
    lines = [l.strip() for l in lyrics.split('\n') if l.strip()]
    clean = [l for l in lines
             if not any(p in l.lower() for p in skip) and len(l) > 8]
    return clean if len(clean) >= 4 else [l for l in lines if len(l) > 8]


def _get_snippet(lyrics: str, n_lines: int = 4) -> Optional[str]:
    clean = _clean_lines(lyrics)
    if len(clean) < n_lines:
        return None
    start = random.randint(0, len(clean) - n_lines)
    return '\n'.join(clean[start:start + n_lines])


# ── Question builders ────────────────────────────────────────────────────

def _build_guess_song(song_choice: Dict, all_songs: List[Dict],
                      hard: bool) -> Optional[Dict]:
    lyrics = _get_lyrics_cached(song_choice["artist"], song_choice["song"])
    if not lyrics:
        return None
    snippet = _get_snippet(lyrics, n_lines=2 if hard else 4)
    if not snippet:
        return None
    others = [s for s in all_songs if s != song_choice]
    options = random.sample(others, min(3, len(others))) + [song_choice]
    random.shuffle(options)
    return {
        "qtype": "guess_song",
        "artist": song_choice["artist"],
        "song": song_choice["song"],
        "snippet": snippet,
        "options": options,
        "answer_index": options.index(song_choice),
        "hard": hard,
    }


def _build_guess_artist(song_choice: Dict, all_songs: List[Dict],
                        hard: bool) -> Optional[Dict]:
    lyrics = _get_lyrics_cached(song_choice["artist"], song_choice["song"])
    if not lyrics:
        return None
    snippet = _get_snippet(lyrics, n_lines=2 if hard else 4)
    if not snippet:
        return None
    others = [s for s in all_songs
              if s["artist"] != song_choice["artist"]]
    random.shuffle(others)
    picked, seen = [], {song_choice["artist"].lower()}
    for s in others:
        if s["artist"].lower() not in seen:
            seen.add(s["artist"].lower())
            picked.append(s)
        if len(picked) == 3:
            break
    if len(picked) < 3:
        return None
    options = picked + [song_choice]
    random.shuffle(options)
    return {
        "qtype": "guess_artist",
        "artist": song_choice["artist"],
        "song": song_choice["song"],
        "snippet": snippet,
        "options": options,
        "answer_index": options.index(song_choice),
        "hard": hard,
    }


def _build_complete_lyric(song_choice: Dict, all_songs: List[Dict],
                           hard: bool) -> Optional[Dict]:
    lyrics = _get_lyrics_cached(song_choice["artist"], song_choice["song"])
    if not lyrics:
        return None
    clean = _clean_lines(lyrics)
    # Need: 3 shown lines + answer line + 3 distractor lines from same song
    if len(clean) < 7:
        return None
    start = random.randint(0, len(clean) - 7)
    shown = clean[start:start + 3]
    answer_line = clean[start + 3]
    rest = [l for l in clean[start + 4:] + clean[:start] if l != answer_line]
    rest = list(dict.fromkeys(rest))  # dedupe, keep order
    if len(rest) < 3:
        return None
    distractors = random.sample(rest, 3)
    options = [{"line": answer_line}] + [{"line": d} for d in distractors]
    random.shuffle(options)
    return {
        "qtype": "complete_lyric",
        "artist": song_choice["artist"],
        "song": song_choice["song"],
        "snippet": '\n'.join(shown),
        "options": options,
        "answer_index": next(i for i, o in enumerate(options)
                             if o["line"] == answer_line),
        "hard": hard,
    }


_BUILDERS = {
    "guess_song": _build_guess_song,
    "guess_artist": _build_guess_artist,
    "complete_lyric": _build_complete_lyric,
}
# Weighted: classic mode most common, new modes keep it fresh
_QTYPE_WEIGHTS = [("guess_song", 0.4), ("guess_artist", 0.3),
                  ("complete_lyric", 0.3)]


def _pick_qtype() -> str:
    r = random.random()
    acc = 0.0
    for name, w in _QTYPE_WEIGHTS:
        acc += w
        if r <= acc:
            return name
    return "guess_song"


def get_quiz_question(exclude_songs: List[Dict] = None,
                      last_artist: str = None,
                      hard: bool = False) -> Optional[Dict]:
    """Build one quiz question of a random type.

    hard=True (streak >= 4): shorter 2-line snippets for guessing modes.
    """
    try:
        all_songs = get_quiz_songs()
        available = [s for s in all_songs if s not in (exclude_songs or [])]
        if not available:
            return None

        different = [s for s in available if s["artist"] != last_artist]
        pool = different if different else available
        random.shuffle(pool)

        # Try a few (qtype, song) combos so one bad lyrics fetch
        # doesn't kill the round.
        for _ in range(6):
            qtype = _pick_qtype()
            song_choice = random.choice(pool)
            q = _BUILDERS[qtype](song_choice, all_songs, hard)
            if q:
                return q
        # Fallback: classic mode over the pool in order
        for song_choice in pool:
            q = _build_guess_song(song_choice, all_songs, hard)
            if q:
                return q
        return None
    except Exception as e:
        logger.error(f"Error getting quiz question: {e}")
        return None


# ── Formatting ───────────────────────────────────────────────────────────

def format_multiple_choice_options(options: List[Dict]) -> str:
    labels = ['🅰️', '🅱️', '🅲', '🅳']
    formatted = []
    for i, option in enumerate(options):
        label = labels[i] if i < len(labels) else f"{chr(65+i)})"
        formatted.append(f"{label} {option['artist']} — {option['song']}")
    return '\n'.join(formatted)


def format_quiz_question(question: Dict, quiz_data: Dict) -> str:
    q_num = quiz_data["total_questions"] + 1
    score = quiz_data["score"]
    hard = question.get("hard", False)

    msg = f"🎵 Round {q_num}"
    if hard:
        msg += " 🔥 HARD"
    if q_num > 1:
        msg += f"  •  Score: {score}/{q_num - 1}"
    msg += "\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    qtype = question.get("qtype", "guess_song")
    if qtype == "guess_artist":
        msg += "🎤 Which *artist* sings these lyrics?\n\n"
        msg += f"❝ {question['snippet']} ❞\n\n"
        labels = ['🅰️', '🅱️', '🅲', '🅳']
        for i, opt in enumerate(question["options"]):
            msg += f"{labels[i]} {opt['artist']}\n"
        msg += "\nReply with A, B, C, or D"
    elif qtype == "complete_lyric":
        msg += "📝 Complete the lyric — what comes next?\n\n"
        msg += f"❝ {question['snippet']}\n➖➖➖ ❓ ➖➖➖ ❞\n\n"
        labels = ['🅰️', '🅱️', '🅲', '🅳']
        for i, opt in enumerate(question["options"]):
            msg += f"{labels[i]} {opt['line']}\n"
        msg += "\nReply with A, B, C, or D"
    else:
        msg += "🎤 Which song has these lyrics?\n\n"
        msg += f"❝ {question['snippet']} ❞\n\n"
        msg += format_multiple_choice_options(question["options"])
        msg += "\n\nReply with A, B, C, or D"

    return msg


# ── Game flow ────────────────────────────────────────────────────────────

def start_quiz(user_id: int, mode: str = "multiple_choice") -> Optional[Dict]:
    try:
        if user_id in active_quizzes and active_quizzes[user_id]["state"] == "active":
            return active_quizzes[user_id]

        question = get_quiz_question()
        if not question:
            return None

        quiz_data = {
            "current_question": question,
            "score": 0,
            "total_questions": 0,
            "state": "active",
            "mode": mode,
            "used_songs": [{
                "artist": question["artist"],
                "song": question["song"]
            }],
            "last_artist": question["artist"],
            "streak": 0,
            "best_streak": 0,
        }

        active_quizzes[user_id] = quiz_data
        return quiz_data

    except Exception as e:
        logger.error(f"Error starting quiz: {e}")
        return None


def _normalize(text: str) -> str:
    return (text.lower().replace(" ", "").replace("-", "")
            .replace("'", "").replace("’", ""))


def _correct_display(question: Dict) -> str:
    qtype = question.get("qtype", "guess_song")
    if qtype == "guess_artist":
        return question["artist"]
    if qtype == "complete_lyric":
        return f"\"{question['options'][question['answer_index']]['line']}\""
    return f"{question['artist']} - {question['song']}"


def _check_free_text(question: Dict, answer: str) -> bool:
    qtype = question.get("qtype", "guess_song")
    ans = _normalize(answer)
    if qtype == "guess_artist":
        return ans == _normalize(question["artist"])
    if qtype == "complete_lyric":
        correct = question["options"][question["answer_index"]]["line"]
        return ans == _normalize(correct)
    song_norm = _normalize(question["song"])
    full_norm = _normalize(f"{question['artist']} - {question['song']}")
    return ans in (song_norm, full_norm)


def check_answer(user_id: int, answer: str) -> Tuple[bool, str]:
    try:
        if user_id not in active_quizzes:
            return False, "No active quiz found! Start one with /quiz"

        quiz = active_quizzes[user_id]
        if quiz["state"] != "active":
            return False, "No active quiz found! Start one with /quiz"

        question = quiz['current_question']
        answer_index = question.get("answer_index", 0)
        answer_clean = answer.strip().upper()

        is_correct = False
        if len(answer_clean) == 1 and answer_clean in 'ABCD':
            is_correct = (ord(answer_clean) - ord('A')) == answer_index
        else:
            is_correct = _check_free_text(question, answer)

        quiz["total_questions"] += 1

        if is_correct:
            quiz["score"] += 1
            quiz["streak"] += 1
            quiz["best_streak"] = max(quiz["best_streak"], quiz["streak"])

            streak_msg = ""
            if quiz["streak"] >= 3:
                streak_msg = f"  🔥 {quiz['streak']} streak!"
            if quiz["streak"] == 4:
                streak_msg += "\n⚡ HARD MODE unlocked — shorter snippets!"

            feedback = f"✅ Correct!{streak_msg}\n"
            feedback += f"The answer was: {_correct_display(question)}"
        else:
            quiz["streak"] = 0
            feedback = f"❌ Not quite!\n"
            feedback += f"The answer was: {_correct_display(question)}"

        hard = quiz["streak"] >= 4
        next_question = get_quiz_question(quiz["used_songs"],
                                          quiz["last_artist"], hard=hard)
        if not next_question:
            quiz["state"] = "completed"
            _record_game(user_id, quiz)
            stats = _format_final_stats(quiz, user_id)
            return is_correct, f"{feedback}\n\n{stats}"

        quiz["current_question"] = next_question
        quiz["used_songs"].append({
            "artist": next_question["artist"],
            "song": next_question["song"]
        })
        quiz["last_artist"] = next_question["artist"]

        next_q_text = format_quiz_question(next_question, quiz)

        return is_correct, f"{feedback}\n\n{next_q_text}"

    except Exception as e:
        logger.error(f"Error checking answer: {e}")
        return False, "Something went wrong! Try /quiz to start a new game"


def _format_final_stats(quiz: Dict, user_id: int = None) -> str:
    score = quiz["score"]
    total = quiz["total_questions"]
    pct = (score / total * 100) if total > 0 else 0
    best_streak = quiz["best_streak"]

    if pct >= 90:
        grade = "🏆 Music Genius!"
    elif pct >= 70:
        grade = "🌟 Great ear!"
    elif pct >= 50:
        grade = "👍 Not bad!"
    else:
        grade = "🎧 Keep listening!"

    msg = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 Quiz Complete!\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Score: {score}/{total} ({pct:.0f}%)\n"
        f"Best streak: {best_streak} 🔥\n"
        f"Rating: {grade}\n"
    )
    if user_id is not None:
        pb = get_personal_best(user_id)
        if pb:
            msg += (f"\n🏅 Personal best: {pb.get('best_pct', 0)}% "
                    f"• {pb.get('best_streak', 0)} streak "
                    f"• {pb.get('games', 0)} games")
    msg += "\n\nStart a new quiz with /quiz!"
    return msg


def get_quiz_stats(user_id: int) -> str:
    try:
        if user_id not in active_quizzes:
            return "No quiz running. Start one with /quiz!"

        quiz = active_quizzes[user_id]
        score = quiz["score"]
        total = quiz["total_questions"]
        pct = (score / total * 100) if total > 0 else 0
        streak = quiz["streak"]
        best_streak = quiz["best_streak"]

        return (
            "🎮 Quiz Stats\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Score: {score}/{total} ({pct:.0f}%)\n"
            f"Current streak: {streak} 🔥\n"
            f"Best streak: {best_streak}\n"
            f"Questions left: ~{len(get_quiz_songs()) - len(quiz.get('used_songs', []))}\n\n"
            "Keep going! 🎵"
        )

    except Exception as e:
        logger.error(f"Error getting quiz stats: {e}")
        return "Error retrieving quiz statistics"


def end_quiz(user_id: int) -> str:
    try:
        if user_id not in active_quizzes:
            return "No active quiz to end! Start one with /quiz 🎵"

        quiz = active_quizzes[user_id]
        _record_game(user_id, quiz)
        stats = _format_final_stats(quiz, user_id)
        del active_quizzes[user_id]

        return stats

    except Exception as e:
        logger.error(f"Error ending quiz: {e}")
        return "Error ending quiz"
