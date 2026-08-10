from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.user import User
from app.models.course import Course
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.flashcard import Flashcard

from app.core.security import get_current_user


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

    # Kullanıcının dersleri
    courses = (
        db.query(Course)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    course_ids = [course.id for course in courses]

    total_courses = len(courses)

    # Kullanıcının hiç dersi yoksa
    if not course_ids:
        return {
            "total_courses": 0,
            "total_quizzes": 0,
            "total_quiz_attempts": 0,
            "average_quiz_score": 0,
            "total_flashcards": 0,
            "flashcards_reviewed": 0,
            "flashcard_accuracy": 0
        }

    # ========================================================
    # QUIZLER
    # ========================================================

    quizzes = (
        db.query(Quiz)
        .filter(
            Quiz.course_id.in_(course_ids)
        )
        .all()
    )

    total_quizzes = len(quizzes)

    quiz_ids = [quiz.id for quiz in quizzes]

    # ========================================================
    # QUIZ DENEMELERİ
    # ========================================================

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

    total_quiz_attempts = len(attempts)

    # Ortalama quiz skoru
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

    # ========================================================
    # FLASHCARDLAR
    # ========================================================

    flashcards = (
        db.query(Flashcard)
        .filter(
            Flashcard.course_id.in_(course_ids)
        )
        .all()
    )

    total_flashcards = len(flashcards)

    # Toplam review
    flashcards_reviewed = sum(
        flashcard.review_count or 0
        for flashcard in flashcards
    )

    # Toplam doğru
    total_correct = sum(
        flashcard.correct_count or 0
        for flashcard in flashcards
    )

    # Toplam yanlış
    total_wrong = sum(
        flashcard.wrong_count or 0
        for flashcard in flashcards
    )

    total_reviews = total_correct + total_wrong

    # Flashcard başarı oranı
    if total_reviews > 0:

        flashcard_accuracy = round(
            (total_correct / total_reviews) * 100,
            2
        )

    else:

        flashcard_accuracy = 0

    # ========================================================
    # SONUÇ
    # ========================================================

    return {
        "total_courses": total_courses,
        "total_quizzes": total_quizzes,
        "total_quiz_attempts": total_quiz_attempts,
        "average_quiz_score": average_quiz_score,
        "total_flashcards": total_flashcards,
        "flashcards_reviewed": flashcards_reviewed,
        "flashcard_accuracy": flashcard_accuracy
    }


# ============================================================
# DERS BAZLI İSTATİSTİKLER
# ============================================================

@router.get("/courses")
def get_course_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Kullanıcının derslerini getir
    courses = (
        db.query(Course)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    results = []

    # Her ders için ayrı ayrı istatistik hesapla
    for course in courses:

        # ====================================================
        # QUIZLER
        # ====================================================

        quizzes = (
            db.query(Quiz)
            .filter(
                Quiz.course_id == course.id
            )
            .all()
        )

        quiz_count = len(quizzes)

        quiz_ids = [
            quiz.id
            for quiz in quizzes
        ]

        # ====================================================
        # QUIZ DENEMELERİ
        # ====================================================

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

        attempt_count = len(attempts)

        # Ortalama quiz skoru
        if attempts:

            average_score = round(
                sum(
                    attempt.score
                    for attempt in attempts
                ) / len(attempts),
                2
            )

        else:

            average_score = 0

        # ====================================================
        # FLASHCARDLAR
        # ====================================================

        flashcards = (
            db.query(Flashcard)
            .filter(
                Flashcard.course_id == course.id
            )
            .all()
        )

        flashcard_count = len(flashcards)

        # Toplam doğru
        total_correct = sum(
            flashcard.correct_count or 0
            for flashcard in flashcards
        )

        # Toplam yanlış
        total_wrong = sum(
            flashcard.wrong_count or 0
            for flashcard in flashcards
        )

        total_reviews = total_correct + total_wrong

        # Flashcard başarı oranı
        if total_reviews > 0:

            flashcard_accuracy = round(
                (total_correct / total_reviews) * 100,
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
            "quiz_count": quiz_count,
            "attempt_count": attempt_count,
            "average_score": average_score,
            "flashcard_count": flashcard_count,
            "flashcard_accuracy": flashcard_accuracy
        })

    return results