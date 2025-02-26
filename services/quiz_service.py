import logging
from typing import List, Dict, Optional, Tuple
import random
from services.lyrics_service import get_song_lyrics
from functools import lru_cache

logger = logging.getLogger(__name__)

# Store active quiz sessions
active_quizzes = {}

# Cache quiz songs to avoid repeated disk/memory operations
@lru_cache(maxsize=1)
def get_quiz_songs() -> List[Dict]:
    """Get cached quiz songs."""
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
        {"artist": "Elvis Presley", "song": "Can't Help Falling in Love"}
    ]

def generate_multiple_choice_options(correct_song: Dict, all_songs: List[Dict]) -> List[Dict]:
    """Generate multiple choice options including the correct answer."""
    # Remove the correct song from the pool to avoid duplicates
    other_songs = [song for song in all_songs if song != correct_song]
    # Randomly select 3 other songs
    wrong_options = random.sample(other_songs, min(3, len(other_songs)))
    # Add the correct answer
    options = wrong_options + [correct_song]
    # Shuffle the options
    random.shuffle(options)
    return options

def format_multiple_choice_options(options: List[Dict]) -> str:
    """Format multiple choice options for display."""
    formatted = []
    for i, option in enumerate(['A', 'B', 'C', 'D'][:len(options)]):
        formatted.append(f"{option}) {options[i]['artist']} - {options[i]['song']}")
    return '\n'.join(formatted)

def get_quiz_question(exclude_songs: List[Dict] = None, last_artist: str = None) -> Optional[Dict]:
    """Get a random quiz question, excluding used songs and avoiding same artist."""
    try:
        # Get songs from cache
        available_songs = [song for song in get_quiz_songs() if song not in (exclude_songs or [])]
        if not available_songs:
            return None

        # If we have a last artist, try to avoid it
        different_artist_songs = [song for song in available_songs if song["artist"] != last_artist]
        song_pool = different_artist_songs if different_artist_songs else available_songs

        # Shuffle the pool once and try songs in order
        random.shuffle(song_pool)

        for song_choice in song_pool:
            lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])
            if not lyrics:
                continue

            lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
            if len(lines) < 4:
                continue

            start_idx = random.randint(0, len(lines) - 4)
            snippet = '\n'.join(lines[start_idx:start_idx + 4])

            # Generate multiple choice options
            options = generate_multiple_choice_options(song_choice, get_quiz_songs())

            return {
                "artist": song_choice["artist"],
                "song": song_choice["song"],
                "snippet": snippet,
                "options": options
            }

        return None

    except Exception as e:
        logger.error(f"Error getting quiz question: {str(e)}")
        return None

def start_quiz(user_id: int, mode: str = "multiple_choice") -> Optional[Dict]:
    """Start a new quiz session for a user."""
    try:
        # Return existing active quiz
        if user_id in active_quizzes and active_quizzes[user_id]["state"] == "active":
            return active_quizzes[user_id]

        # Get first question
        question = get_quiz_question()
        if not question:
            return None

        # Initialize quiz with minimal data structure
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
            "last_artist": question["artist"]
        }

        active_quizzes[user_id] = quiz_data
        return quiz_data

    except Exception as e:
        logger.error(f"Error starting quiz: {str(e)}")
        return None

def check_answer(user_id: int, answer: str) -> Tuple[bool, str]:
    """Check the user's answer and return feedback."""
    try:
        if user_id not in active_quizzes:
            return False, "No active quiz found! Start a new quiz with /quiz"

        quiz = active_quizzes[user_id]
        if quiz["state"] != "active":
            return False, "No active quiz found! Start a new quiz with /quiz"

        correct_answer = f"{quiz['current_question']['artist']} - {quiz['current_question']['song']}"

        # Simple case-insensitive comparison
        answer_lower = answer.lower().replace(" ", "")
        correct_lower = correct_answer.lower().replace(" ", "")
        is_correct = answer_lower == correct_lower

        if is_correct:
            quiz["score"] += 1
            feedback = "🎯 Correct! You're amazing! +1 point"
        else:
            feedback = f"❌ Not quite! The answer was: {correct_answer}"

        quiz["total_questions"] += 1

        # Get next question, avoiding the current artist
        next_question = get_quiz_question(quiz["used_songs"], quiz["last_artist"])
        if not next_question:
            quiz["state"] = "completed"
            return is_correct, f"{feedback}\n\nℹ️ Quiz completed! You've gone through all available songs."

        # Update quiz with next question
        quiz["current_question"] = next_question
        quiz["used_songs"].append({
            "artist": next_question["artist"],
            "song": next_question["song"]
        })
        quiz["last_artist"] = next_question["artist"]

        return is_correct, feedback

    except Exception as e:
        logger.error(f"Error checking answer: {str(e)}")
        return False, "Sorry, something went wrong! Try /quiz to start a new game"

def get_quiz_stats(user_id: int) -> str:
    """Get the user's current quiz statistics."""
    try:
        if user_id not in active_quizzes:
            return "No quiz statistics available. Start playing with /quiz!"

        quiz = active_quizzes[user_id]
        score = quiz["score"]
        total = quiz["total_questions"]
        percentage = (score / total * 100) if total > 0 else 0

        return (
            "🎮 Quiz Statistics:\n"
            f"✨ Score: {score}/{total}\n"
            f"📊 Accuracy: {percentage:.1f}%\n"
            "Keep going! You're doing great! 🌟"
        )

    except Exception as e:
        logger.error(f"Error getting quiz stats: {str(e)}")
        return "Error retrieving quiz statistics"

def end_quiz(user_id: int) -> str:
    """End the quiz and return final statistics."""
    try:
        if user_id not in active_quizzes:
            return "No active quiz to end!"

        stats = get_quiz_stats(user_id)
        del active_quizzes[user_id]

        return f"Quiz ended!\n\n{stats}\n\nStart a new quiz anytime with /quiz 🎵"

    except Exception as e:
        logger.error(f"Error ending quiz: {str(e)}")
        return "Error ending quiz"