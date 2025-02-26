import os
import random
import logging
from typing import Dict, List, Optional, Tuple
from services.lyrics_service import get_song_lyrics

logger = logging.getLogger(__name__)

# Store active quiz sessions
active_quizzes: Dict[int, Dict] = {}

# Sample quiz questions (we'll expand this later)
QUIZ_SONGS = [
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

def start_quiz(user_id: int) -> Optional[Dict]:
    """Start a new quiz session for a user."""
    try:
        if user_id in active_quizzes:
            logger.info(f"User {user_id} already has an active quiz")
            return active_quizzes[user_id]

        # Pick a random song
        song_choice = random.choice(QUIZ_SONGS)
        lyrics = get_song_lyrics(song_choice["artist"], song_choice["song"])

        if not lyrics:
            logger.error(f"Could not fetch lyrics for {song_choice['artist']} - {song_choice['song']}")
            return None

        # Split lyrics into lines and get a random 4-line snippet
        lines = [line for line in lyrics.split('\n') if line.strip()]
        if len(lines) < 4:
            logger.error("Not enough lines in lyrics")
            return None

        start_idx = random.randint(0, len(lines) - 4)
        snippet = '\n'.join(lines[start_idx:start_idx + 4])

        quiz_data = {
            "current_question": {
                "artist": song_choice["artist"],
                "song": song_choice["song"],
                "snippet": snippet
            },
            "score": 0,
            "total_questions": 0,
            "state": "active"
        }

        active_quizzes[user_id] = quiz_data
        logger.info(f"Started new quiz for user {user_id}")
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
        correct_answer = f"{quiz['current_question']['artist']} - {quiz['current_question']['song']}"
        
        # Calculate similarity score (basic for now)
        answer_lower = answer.lower().replace(" ", "")
        correct_lower = correct_answer.lower().replace(" ", "")
        is_correct = answer_lower == correct_lower

        if is_correct:
            quiz["score"] += 1
            feedback = "🎯 Correct! You're amazing! +1 point"
        else:
            feedback = f"❌ Not quite! The answer was: {correct_answer}"

        quiz["total_questions"] += 1
        
        # Start new question
        new_quiz = start_quiz(user_id)
        if not new_quiz:
            return is_correct, f"{feedback}\n\nℹ️ No more questions available"

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
