import logging
from typing import List, Dict, Optional, Tuple
import random
from services.lyrics_service import get_song_lyrics
from functools import lru_cache

logger = logging.getLogger(__name__)

active_quizzes = {}

@lru_cache(maxsize=1)
def get_quiz_songs() -> List[Dict]:
    return [
        {"artist": "Queen", "song": "Bohemian Rhapsody"},
        {"artist": "The Beatles", "song": "Hey Jude"},
        {"artist": "Michael Jackson", "song": "Billie Jean"},
        {"artist": "Adele", "song": "Rolling in the Deep"},
        {"artist": "Ed Sheeran", "song": "Shape of You"},
        {"artist": "Taylor Swift", "song": "Shake It Off"},
        {"artist": "Whitney Houston", "song": "I Will Always Love You"},
        {"artist": "Journey", "song": "Don't Stop Believin'"},
        {"artist": "Lady Gaga", "song": "Bad Romance"},
        {"artist": "Elvis Presley", "song": "Can't Help Falling in Love"},
        {"artist": "Tyla", "song": "Water"},
        {"artist": "Dua Lipa", "song": "Levitating"},
        {"artist": "Harry Styles", "song": "As It Was"},
        {"artist": "Olivia Rodrigo", "song": "drivers license"},
        {"artist": "The Weeknd", "song": "Blinding Lights"},
        {"artist": "Billie Eilish", "song": "bad guy"},
        {"artist": "Bruno Mars", "song": "Just the Way You Are"},
        {"artist": "Rihanna", "song": "Umbrella"},
        {"artist": "Eminem", "song": "Lose Yourself"},
        {"artist": "Coldplay", "song": "Yellow"},
        {"artist": "Imagine Dragons", "song": "Believer"},
        {"artist": "Ariana Grande", "song": "thank u, next"},
        {"artist": "Post Malone", "song": "Circles"},
        {"artist": "Kendrick Lamar", "song": "HUMBLE."},
        {"artist": "SZA", "song": "Kill Bill"},
        {"artist": "Miley Cyrus", "song": "Flowers"},
        {"artist": "Arctic Monkeys", "song": "Do I Wanna Know?"},
        {"artist": "Beyonce", "song": "Halo"},
        {"artist": "Drake", "song": "Hotline Bling"},
        {"artist": "Nirvana", "song": "Smells Like Teen Spirit"},
        {"artist": "John Legend", "song": "All of Me"},
        {"artist": "Maroon 5", "song": "Sugar"},
        {"artist": "Sia", "song": "Chandelier"},
        {"artist": "Sam Smith", "song": "Stay With Me"},
        {"artist": "Lana Del Rey", "song": "Summertime Sadness"},
        {"artist": "Fleetwood Mac", "song": "Dreams"},
        {"artist": "Hozier", "song": "Take Me to Church"},
        {"artist": "Gotye", "song": "Somebody That I Used to Know"},
        {"artist": "Pharrell Williams", "song": "Happy"},
        {"artist": "Lewis Capaldi", "song": "Someone You Loved"},
    ]

def generate_multiple_choice_options(correct_song: Dict, all_songs: List[Dict]) -> List[Dict]:
    other_songs = [song for song in all_songs if song != correct_song]
    wrong_options = random.sample(other_songs, min(3, len(other_songs)))
    options = wrong_options + [correct_song]
    random.shuffle(options)
    return options

def format_multiple_choice_options(options: List[Dict]) -> str:
    labels = ['🅰️', '🅱️', '🅲', '🅳']
    formatted = []
    for i, option in enumerate(options):
        label = labels[i] if i < len(labels) else f"{chr(65+i)})"
        formatted.append(f"{label} {options[i]['artist']} — {options[i]['song']}")
    return '\n'.join(formatted)

def _get_snippet(lyrics: str) -> Optional[str]:
    lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
    if len(lines) < 3:
        return None

    skip_patterns = ['chorus', 'verse', 'bridge', 'intro', 'outro', '[', ']']
    clean_lines = []
    for line in lines:
        if not any(p in line.lower() for p in skip_patterns):
            clean_lines.append(line)

    if len(clean_lines) < 3:
        clean_lines = lines

    snippet_length = min(4, len(clean_lines))
    max_start = len(clean_lines) - snippet_length
    if max_start <= 0:
        return '\n'.join(clean_lines[:snippet_length])

    start_idx = random.randint(0, max_start)
    return '\n'.join(clean_lines[start_idx:start_idx + snippet_length])

def get_quiz_question(exclude_songs: List[Dict] = None, last_artist: str = None) -> Optional[Dict]:
    try:
        available_songs = [song for song in get_quiz_songs() if song not in (exclude_songs or [])]
        if not available_songs:
            return None

        different_artist_songs = [song for song in available_songs if song["artist"] != last_artist]
        song_pool = different_artist_songs if different_artist_songs else available_songs

        random.shuffle(song_pool)

        for song_choice in song_pool:
            lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])
            if not lyrics:
                continue

            snippet = _get_snippet(lyrics)
            if not snippet:
                continue

            options = generate_multiple_choice_options(song_choice, get_quiz_songs())

            return {
                "artist": song_choice["artist"],
                "song": song_choice["song"],
                "snippet": snippet,
                "options": options
            }

        return None

    except Exception as e:
        logger.error(f"Error getting quiz question: {e}")
        return None

def format_quiz_question(question: Dict, quiz_data: Dict) -> str:
    q_num = quiz_data["total_questions"] + 1
    score = quiz_data["score"]

    msg = (
        f"🎵 Round {q_num}"
    )
    if q_num > 1:
        msg += f"  •  Score: {score}/{q_num - 1}"
    msg += "\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "🎤 Which song has these lyrics?\n\n"
    msg += f"❝ {question['snippet']} ❞\n\n"
    msg += format_multiple_choice_options(question['options'])
    msg += "\n\nReply with A, B, C, or D"

    return msg

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

def check_answer(user_id: int, answer: str) -> Tuple[bool, str]:
    try:
        if user_id not in active_quizzes:
            return False, "No active quiz found! Start one with /quiz"

        quiz = active_quizzes[user_id]
        if quiz["state"] != "active":
            return False, "No active quiz found! Start one with /quiz"

        question = quiz['current_question']
        correct_answer = f"{question['artist']} - {question['song']}"
        answer_clean = answer.strip().upper()

        is_correct = False

        if len(answer_clean) == 1 and answer_clean in 'ABCD':
            idx = ord(answer_clean) - ord('A')
            options = question['options']
            if idx < len(options):
                selected = options[idx]
                is_correct = (selected['artist'] == question['artist'] and
                            selected['song'] == question['song'])
        else:
            answer_norm = answer.lower().replace(" ", "").replace("-", "")
            correct_norm = correct_answer.lower().replace(" ", "").replace("-", "")
            is_correct = answer_norm == correct_norm

        quiz["total_questions"] += 1

        if is_correct:
            quiz["score"] += 1
            quiz["streak"] += 1
            quiz["best_streak"] = max(quiz["best_streak"], quiz["streak"])

            streak_msg = ""
            if quiz["streak"] >= 3:
                streak_msg = f"  🔥 {quiz['streak']} streak!"

            feedback = f"✅ Correct!{streak_msg}\n"
            feedback += f"The answer was: {correct_answer}"
        else:
            quiz["streak"] = 0
            feedback = f"❌ Not quite!\n"
            feedback += f"The answer was: {correct_answer}"

        next_question = get_quiz_question(quiz["used_songs"], quiz["last_artist"])
        if not next_question:
            quiz["state"] = "completed"
            stats = _format_final_stats(quiz)
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

def _format_final_stats(quiz: Dict) -> str:
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
        f"Rating: {grade}\n\n"
        "Start a new quiz with /quiz!"
    )
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
        stats = _format_final_stats(quiz)
        del active_quizzes[user_id]

        return stats

    except Exception as e:
        logger.error(f"Error ending quiz: {e}")
        return "Error ending quiz"
