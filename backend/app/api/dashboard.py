from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.user import User
from app.models.course import Course
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.flashcard import Flashcard
from app.models.achievement import Achievement
from app.models.event import Event
from app.models.goal import Goal

from app.core.security import get_current_user

from app.services.ai_service import generate_study_recommendation


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # =========================================================
    # KULLANICININ DERSLERİ
    # =========================================================

    courses = (
        db.query(Course)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    course_ids = [
        course.id
        for course in courses
    ]

    # =========================================================
    # QUIZLER
    # =========================================================

    if course_ids:

        quizzes = (
            db.query(Quiz)
            .filter(
                Quiz.course_id.in_(course_ids)
            )
            .all()
        )

    else:

        quizzes = []

    quiz_ids = [
        quiz.id
        for quiz in quizzes
    ]

    # =========================================================
    # QUIZ DENEMELERİ
    # =========================================================

    if quiz_ids:

        attempts = (
            db.query(QuizAttempt)
            .filter(
                QuizAttempt.quiz_id.in_(quiz_ids)
            )
            .all()
        )

    else:

        attempts = []

    total_quizzes = len(quizzes)

    total_quiz_attempts = len(attempts)

    if attempts:

        average_quiz_score = round(
            sum(
                attempt.score
                for attempt in attempts
            ) / len(attempts),
            2
        )

    else:

        average_quiz_score = 0

    # =========================================================
    # DERS BAZLI QUIZ PERFORMANSI
    # =========================================================

    weakest_course = None
    weakest_course_score = None

    for course in courses:

        course_quizzes = (
            db.query(Quiz)
            .filter(
                Quiz.course_id == course.id
            )
            .all()
        )

        course_quiz_ids = [
            quiz.id
            for quiz in course_quizzes
        ]

        if not course_quiz_ids:
            continue

        course_attempts = (
            db.query(QuizAttempt)
            .filter(
                QuizAttempt.quiz_id.in_(course_quiz_ids)
            )
            .all()
        )

        if not course_attempts:
            continue

        course_average = (
            sum(
                attempt.score
                for attempt in course_attempts
            )
            / len(course_attempts)
        )

        if (
            weakest_course_score is None
            or course_average < weakest_course_score
        ):

            weakest_course_score = course_average

            weakest_course = course.name

    # =========================================================
    # FLASHCARDLAR
    # =========================================================

    if course_ids:

        flashcards = (
            db.query(Flashcard)
            .filter(
                Flashcard.course_id.in_(course_ids)
            )
            .all()
        )

    else:

        flashcards = []

    total_flashcards = len(flashcards)

    total_reviews = sum(
        flashcard.review_count or 0
        for flashcard in flashcards
    )

    total_correct = sum(
        flashcard.correct_count or 0
        for flashcard in flashcards
    )

    total_wrong = sum(
        flashcard.wrong_count or 0
        for flashcard in flashcards
    )

    if total_correct + total_wrong > 0:

        flashcard_accuracy = round(
            (
                total_correct
                / (total_correct + total_wrong)
            ) * 100,
            2
        )

    else:

        flashcard_accuracy = 0

    # =========================================================
    # BAŞARILAR
    # =========================================================

    achievements = (
        db.query(Achievement)
        .filter(
            Achievement.user_id == current_user.id
        )
        .all()
    )

    total_achievements = len(achievements)

    completed_achievements = sum(
        1
        for achievement in achievements
        if achievement.completed
    )

    # =========================================================
    # BUGÜN
    # =========================================================

    now = datetime.now(timezone.utc)

    start_of_day = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    end_of_day = now.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999
    )

    # =========================================================
    # BUGÜNKÜ ETKİNLİKLER
    # =========================================================

    today_events = (
        db.query(Event)
        .filter(
            Event.user_id == current_user.id,
            Event.start_date >= start_of_day,
            Event.start_date <= end_of_day
        )
        .order_by(
            Event.start_date.asc()
        )
        .all()
    )

    # =========================================================
    # YAKLAŞAN SINAVLAR
    # =========================================================

    upcoming_exams = (
        db.query(Event)
        .filter(
            Event.user_id == current_user.id,
            Event.event_type == "exam",
            Event.start_date >= now
        )
        .order_by(
            Event.start_date.asc()
        )
        .limit(5)
        .all()
    )

    # =========================================================
    # SON BAŞARILAR
    # =========================================================

    recent_achievements = (
        db.query(Achievement)
        .filter(
            Achievement.user_id == current_user.id,
            Achievement.completed == True
        )
        .order_by(
            Achievement.id.desc()
        )
        .limit(5)
        .all()
    )

    # =========================================================
    # AKTİF HEDEFLER
    # =========================================================

    today = now.date()

    active_goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == current_user.id,
            Goal.completed == False,
            Goal.start_date <= today,
            Goal.end_date >= today
        )
        .order_by(
            Goal.end_date.asc()
        )
        .all()
    )

    # =========================================================
    # HEDEF İLERLEMELERİ
    # =========================================================

    goal_results = []

    for goal in active_goals:

        if goal.target_value > 0:

            progress = round(
                (
                    goal.current_value
                    / goal.target_value
                ) * 100,
                2
            )

        else:

            progress = 0

        if progress > 100:
            progress = 100

        goal_results.append({

            "id": goal.id,

            "title": goal.title,

            "goal_type": goal.goal_type,

            "current_value": goal.current_value,

            "target_value": goal.target_value,

            "progress": progress,

            "start_date": goal.start_date,

            "end_date": goal.end_date,

            "course_id": goal.course_id,

            "completed": goal.completed

        })

    # =========================================================
    # AI ÇALIŞMA ÖNERİSİ
    # =========================================================

    try:

        ai_recommendation = generate_study_recommendation(

            total_courses=len(courses),

            total_quizzes=total_quizzes,

            quiz_average=average_quiz_score,

            total_flashcards=total_flashcards,

            flashcard_reviews=total_reviews,

            weakest_course=weakest_course,

            # Pomodoro olmadığı için gerçek çalışma
            # süresi şu anda ölçülmüyor.
            study_hours=0

        )

        ai_recommendation_result = {

            "message":
                ai_recommendation.message,

            "priority":
                ai_recommendation.priority,

            "recommended_action":
                ai_recommendation.recommended_action

        }

    except Exception:

        ai_recommendation_result = {

            "message":
                "Şu anda AI önerisi oluşturulamadı.",

            "priority":
                "low",

            "recommended_action":
                "Derslerinden birini seçerek çalışmaya başlayabilirsin."

        }

    # =========================================================
    # DASHBOARD SONUCU
    # =========================================================

    return {

        "user": {

            "id": current_user.id,

            "username": getattr(
                current_user,
                "username",
                None
            )

        },

        "summary": {

            "total_courses": len(courses),

            "total_quizzes": total_quizzes,

            "total_quiz_attempts": total_quiz_attempts,

            "average_quiz_score":
                average_quiz_score,

            "total_flashcards":
                total_flashcards,

            "flashcards_reviewed":
                total_reviews,

            "flashcard_accuracy":
                flashcard_accuracy,

            "total_achievements":
                total_achievements,

            "completed_achievements":
                completed_achievements

        },

        # =====================================================
        # AKTİF DERSLER
        # =====================================================

        "active_courses": [

            {
                "id": course.id,
                "name": course.name
            }

            for course in courses

        ],

        # =====================================================
        # BUGÜNKÜ ETKİNLİKLER
        # =====================================================

        "today_events": [

            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "event_type": event.event_type,
                "course_id": event.course_id,
                "start_date": event.start_date,
                "end_date": event.end_date,
                "completed": event.completed
            }

            for event in today_events

        ],

        # =====================================================
        # YAKLAŞAN SINAVLAR
        # =====================================================

        "upcoming_exams": [

            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "course_id": event.course_id,
                "start_date": event.start_date,
                "end_date": event.end_date,
                "completed": event.completed
            }

            for event in upcoming_exams

        ],

        # =====================================================
        # SON BAŞARILAR
        # =====================================================

        "recent_achievements": [

            {
                "id": achievement.id,

                "achievement_type":
                    achievement.achievement_type,

                "title":
                    achievement.title,

                "description":
                    achievement.description,

                "completed":
                    achievement.completed

            }

            for achievement in recent_achievements

        ],

        # =====================================================
        # AKTİF HEDEFLER
        # =====================================================

        "active_goals":
            goal_results,

        # =====================================================
        # AI ÖNERİSİ
        # =====================================================

        "ai_recommendation":
            ai_recommendation_result

    }