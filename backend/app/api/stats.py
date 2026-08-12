from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.user import User
from app.models.course import Course
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.flashcard import Flashcard
from app.models.achievement import Achievement
from app.models.study_session import StudySession

from app.core.security import get_current_user
from datetime import datetime, timezone, timedelta


router = APIRouter(
    prefix="/stats",
    tags=["Statistics"]
)


# ============================================================
# GENEL İSTATİSTİKLER
# ============================================================

@router.get("/summary")
def get_stats_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    courses = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    course_ids = [course.id for course in courses]
    total_courses = len(courses)

    if not course_ids:
        return {
            "total_courses": 0,
            "total_study_minutes": 0,
            "total_study_hours": 0,
            "total_quizzes": 0,
            "total_quiz_attempts": 0,
            "average_quiz_score": 0,
            "total_quiz_correct": 0,
            "total_quiz_wrong": 0,
            "total_quiz_questions": 0,
            "total_flashcards": 0,
            "flashcards_reviewed": 0,
            "flashcard_correct": 0,
            "flashcard_wrong": 0,
            "flashcard_accuracy": 0,
            "total_achievements": 0
        }

    quizzes = (
        db.query(Quiz)
        .filter(Quiz.course_id.in_(course_ids))
        .all()
    )

    total_quizzes = len(quizzes)
    quiz_ids = [quiz.id for quiz in quizzes]

    if quiz_ids:
        attempts = (
            db.query(QuizAttempt)
            .filter(QuizAttempt.quiz_id.in_(quiz_ids))
            .all()
        )
    else:
        attempts = []

    total_quiz_attempts = len(attempts)

    if attempts:
        average_quiz_score = round(
            sum(attempt.score for attempt in attempts) / len(attempts),
            2
        )

        total_quiz_correct = sum(
            attempt.correct_count for attempt in attempts
        )

        total_quiz_wrong = sum(
            attempt.wrong_count for attempt in attempts
        )

        total_quiz_questions = sum(
            attempt.total_questions for attempt in attempts
        )
    else:
        average_quiz_score = 0
        total_quiz_correct = 0
        total_quiz_wrong = 0
        total_quiz_questions = 0

    # ========================================================
    # ÇALIŞMA SÜRELERİ
    # ========================================================

    study_sessions = (
        db.query(StudySession)
        .filter(StudySession.user_id == current_user.id)
        .all()
    )

    total_study_minutes = sum(
        session.duration_minutes or 0
        for session in study_sessions
    )

    total_study_hours = round(total_study_minutes / 60, 2)

    # ========================================================
    # FLASHCARDLAR
    # ========================================================

    flashcards = (
        db.query(Flashcard)
        .filter(Flashcard.course_id.in_(course_ids))
        .all()
    )

    total_flashcards = len(flashcards)

    flashcards_reviewed = sum(
        flashcard.review_count or 0
        for flashcard in flashcards
    )

    flashcard_correct = sum(
        flashcard.correct_count or 0
        for flashcard in flashcards
    )

    flashcard_wrong = sum(
        flashcard.wrong_count or 0
        for flashcard in flashcards
    )

    total_reviews = flashcard_correct + flashcard_wrong

    if total_reviews > 0:
        flashcard_accuracy = round(
            (flashcard_correct / total_reviews) * 100,
            2
        )
    else:
        flashcard_accuracy = 0

    # ========================================================
    # ACHIEVEMENTS
    # ========================================================

    total_achievements = (
        db.query(Achievement)
        .filter(
            Achievement.user_id == current_user.id,
            Achievement.completed == True
        )
        .count()
    )

    return {
        "total_courses": total_courses,

        "total_study_minutes": total_study_minutes,
        "total_study_hours": total_study_hours,

        "total_quizzes": total_quizzes,
        "total_quiz_attempts": total_quiz_attempts,
        "average_quiz_score": average_quiz_score,
        "total_quiz_correct": total_quiz_correct,
        "total_quiz_wrong": total_quiz_wrong,
        "total_quiz_questions": total_quiz_questions,

        "total_flashcards": total_flashcards,
        "flashcards_reviewed": flashcards_reviewed,
        "flashcard_correct": flashcard_correct,
        "flashcard_wrong": flashcard_wrong,
        "flashcard_accuracy": flashcard_accuracy,

        "total_achievements": total_achievements
    }


# ============================================================
# DERS BAZLI İSTATİSTİKLER
# ============================================================

@router.get("/courses")
def get_course_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    courses = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    results = []

    for course in courses:

        # ====================================================
        # ÇALIŞMA SÜRELERİ
        # ====================================================

        study_sessions = (
            db.query(StudySession)
            .filter(
                StudySession.user_id == current_user.id,
                StudySession.course_id == course.id
            )
            .all()
        )

        study_minutes = sum(
            session.duration_minutes or 0
            for session in study_sessions
        )

        study_hours = round(study_minutes / 60, 2)

        # ====================================================
        # QUIZLER
        # ====================================================

        quizzes = (
            db.query(Quiz)
            .filter(Quiz.course_id == course.id)
            .all()
        )

        quiz_count = len(quizzes)
        quiz_ids = [quiz.id for quiz in quizzes]

        if quiz_ids:
            attempts = (
                db.query(QuizAttempt)
                .filter(QuizAttempt.quiz_id.in_(quiz_ids))
                .all()
            )
        else:
            attempts = []

        attempt_count = len(attempts)

        if attempts:
            average_score = round(
                sum(attempt.score for attempt in attempts) / len(attempts),
                2
            )

            quiz_correct = sum(
                attempt.correct_count for attempt in attempts
            )

            quiz_wrong = sum(
                attempt.wrong_count for attempt in attempts
            )
        else:
            average_score = 0
            quiz_correct = 0
            quiz_wrong = 0

        # ====================================================
        # FLASHCARDLAR
        # ====================================================

        flashcards = (
            db.query(Flashcard)
            .filter(Flashcard.course_id == course.id)
            .all()
        )

        flashcard_count = len(flashcards)

        flashcard_correct = sum(
            flashcard.correct_count or 0
            for flashcard in flashcards
        )

        flashcard_wrong = sum(
            flashcard.wrong_count or 0
            for flashcard in flashcards
        )

        total_reviews = flashcard_correct + flashcard_wrong

        if total_reviews > 0:
            flashcard_accuracy = round(
                (flashcard_correct / total_reviews) * 100,
                2
            )
        else:
            flashcard_accuracy = 0

        # ====================================================
        # DERS SONUCUNU EKLE
        # ====================================================

        results.append({
            "course_id": course.id,
            "course_name": course.name,

            "study_minutes": study_minutes,
            "study_hours": study_hours,

            "quiz_count": quiz_count,
            "attempt_count": attempt_count,
            "average_score": average_score,
            "quiz_correct": quiz_correct,
            "quiz_wrong": quiz_wrong,

            "flashcard_count": flashcard_count,
            "flashcard_correct": flashcard_correct,
            "flashcard_wrong": flashcard_wrong,
            "flashcard_accuracy": flashcard_accuracy
        })

    return results

# ============================================================
# ÇALIŞMA SERİSİ (STREAK)
# ============================================================

@router.get("/streak")
def get_streak(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sessions = (
        db.query(StudySession.study_date)
        .filter(
            StudySession.user_id == current_user.id
        )
        .distinct()
        .order_by(
            StudySession.study_date.desc()
        )
        .all()
    )

    study_dates = [
        session.study_date
        for session in sessions
    ]

    if not study_dates:
        return {
            "current_streak": 0,
            "longest_streak": 0
        }

    # ========================================================
    # CURRENT STREAK
    # ========================================================

    today = datetime.now(timezone.utc).date()

    date_set = set(study_dates)

    # Kullanıcı bugün çalışmadıysa,
    # dün çalıştıysa seri dünden devam eder.
    if today in date_set:
        current_date = today
    elif (today - timedelta(days=1)) in date_set:
        current_date = today - timedelta(days=1)
    else:
        current_date = None

    current_streak = 0

    if current_date is not None:

        while current_date in date_set:

            current_streak += 1

            current_date = (
                current_date - timedelta(days=1)
            )

    # ========================================================
    # LONGEST STREAK
    # ========================================================

    longest_streak = 0
    running_streak = 0
    previous_date = None

    for study_date in sorted(date_set):

        if (
            previous_date is not None
            and study_date == previous_date + timedelta(days=1)
        ):
            running_streak += 1

        else:
            running_streak = 1

        if running_streak > longest_streak:
            longest_streak = running_streak

        previous_date = study_date

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak
    }

# ============================================================
# HAFTALIK ÇALIŞMA İSTATİSTİKLERİ
# ============================================================

@router.get("/weekly")
def get_weekly_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today = datetime.now(timezone.utc).date()

    # Pazartesiyi haftanın başlangıcı kabul ediyoruz
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    sessions = (
        db.query(StudySession)
        .filter(
            StudySession.user_id == current_user.id,
            StudySession.study_date >= week_start,
            StudySession.study_date <= week_end
        )
        .all()
    )

    # ========================================================
    # GÜN BAZLI ÇALIŞMA
    # ========================================================

    daily_minutes = {}

    for i in range(7):
        date = week_start + timedelta(days=i)

        daily_minutes[str(date)] = 0

    for session in sessions:

        date_key = str(session.study_date)

        if date_key in daily_minutes:
            daily_minutes[date_key] += (
                session.duration_minutes or 0
            )

    daily_hours = {
        date: round(minutes / 60, 2)
        for date, minutes in daily_minutes.items()
    }

    # ========================================================
    # TOPLAM HAFTALIK ÇALIŞMA
    # ========================================================

    total_weekly_minutes = sum(
        daily_minutes.values()
    )

    total_weekly_hours = round(
        total_weekly_minutes / 60,
        2
    )

    # ========================================================
    # DERS BAZLI ÇALIŞMA
    # ========================================================

    course_stats = {}

    courses = (
        db.query(Course)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    for course in courses:

        course_minutes = sum(
            session.duration_minutes or 0
            for session in sessions
            if session.course_id == course.id
        )

        course_stats[str(course.id)] = {
            "course_id": course.id,
            "course_name": course.name,
            "study_minutes": course_minutes,
            "study_hours": round(
                course_minutes / 60,
                2
            )
        }

    return {
        "week_start": week_start,
        "week_end": week_end,
        "total_weekly_minutes": total_weekly_minutes,
        "total_weekly_hours": total_weekly_hours,
        "daily_minutes": daily_minutes,
        "daily_hours": daily_hours,
        "courses": list(course_stats.values())
    }
