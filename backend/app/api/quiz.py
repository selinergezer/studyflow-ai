import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.models.quiz import Quiz
from app.models.question import Question
from app.models.document import Document
from app.models.course import Course
from app.models.user import User
from app.models.achievement import Achievement
from app.models.study_room import StudyRoom
from app.models.study_room_member import StudyRoomMember
from app.models.study_room_message import StudyRoomMessage

from app.core.security import get_current_user
from app.services.ai_service import (
    LMStudioServiceError,
    generate_quiz,
    generate_quiz_questions_stream,
)

from app.schemas.quiz import QuizSubmit
from app.models.quiz_attempt import QuizAttempt

from app.services.goal_service import update_goal_progress


router = APIRouter(
    prefix="/quizzes",
    tags=["Quizzes"]
)

logger = logging.getLogger("uvicorn.error.studyflow.quiz")
_PREVIOUS_DOCUMENT_QUESTION_LIMIT = 12


def _is_correct_multiple_choice(
    user_answer: Optional[str],
    correct_answer: Optional[str],
) -> bool:
    if user_answer is None or correct_answer is None:
        return False

    normalized_user_answer = user_answer.strip().upper()
    normalized_correct_answer = correct_answer.strip().upper()
    valid_choices = {"A", "B", "C", "D", "E"}

    return (
        normalized_user_answer in valid_choices
        and normalized_correct_answer in valid_choices
        and normalized_user_answer == normalized_correct_answer
    )

def _get_accessible_quiz(
    db: Session,
    quiz_id: int,
    current_user: User,
):
    # Önce quiz'i bul
    quiz = (
        db.query(Quiz)
        .filter(Quiz.id == quiz_id)
        .first()
    )

    if quiz is None:
        return None

    # Quiz sahibi ise doğrudan erişebilir
    if (
        db.query(Course)
        .filter(
            Course.id == quiz.course_id,
            Course.user_id == current_user.id,
        )
        .first()
        is not None
    ):
        return quiz

    # Quiz bir Study Room'da paylaşılmış mı?
    shared_room = (
        db.query(StudyRoom)
        .join(
            StudyRoomMessage,
            StudyRoomMessage.room_id == StudyRoom.id,
        )
        .join(
            StudyRoomMember,
            StudyRoomMember.room_id == StudyRoom.id,
        )
        .filter(
            StudyRoomMessage.material_type == "quiz",
            StudyRoomMessage.material_id == quiz_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True,
            StudyRoom.is_active == True,
        )
        .first()
    )

    if shared_room is not None:
        return quiz

    return None

def _get_previous_document_questions(
    db: Session,
    document_id: int,
) -> list[dict]:
    quiz_rows = (
        db.query(Quiz.id)
        .filter(Quiz.document_id == document_id)
        .order_by(Quiz.id.asc())
        .all()
    )
    historical_quiz_ids = [quiz_id for (quiz_id,) in quiz_rows]
    questions = (
        db.query(Question)
        .join(Quiz, Question.quiz_id == Quiz.id)
        .filter(Quiz.document_id == document_id)
        .order_by(Question.id.desc())
        .limit(_PREVIOUS_DOCUMENT_QUESTION_LIMIT)
        .all()
    )
    previous_questions = []

    for question in questions:
        correct_letter = (question.correct_answer or "").strip().casefold()
        correct_option = getattr(question, f"option_{correct_letter}", "")
        previous_questions.append({
            "quiz_id": question.quiz_id,
            "question_text": question.question_text or "",
            "correct_option": correct_option or "",
            "explanation": question.explanation or "",
        })

    logger.info(
        "CrossQuiz history document=%s previous_quiz_count=%s quizzes=%s "
        "questions=%s",
        document_id,
        len(historical_quiz_ids),
        historical_quiz_ids,
        len(previous_questions),
    )
    for historical_question in previous_questions:
        logger.info(
            "CrossQuiz historical question quiz=%s preview=%r",
            historical_question["quiz_id"],
            historical_question["question_text"][:80],
        )

    return previous_questions


# =========================================================
# QUIZ OLUŞTUR
# =========================================================

@router.post("/generate")
def generate_quiz_endpoint(
    document_id: int,
    question_count: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Belgeyi bul ve kullanıcının kendi belgesi olduğunu kontrol et
    document = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(
            Document.id == document_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Belge bulunamadı."
        )

    # Soru sayısı kontrolü
    if question_count < 1 or question_count > 20:
        raise HTTPException(
            status_code=400,
            detail="Soru sayısı 1 ile 20 arasında olmalıdır."
        )

    # PDF metninden AI ile quiz oluştur
    logger.info(
        "Quiz generation started: document_id=%s questions=%s",
        document_id,
        question_count,
    )
    previous_questions = _get_previous_document_questions(db, document.id)

    try:
        generated_quiz = generate_quiz(
            document.text,
            question_count,
            previous_questions=previous_questions,
        )
    except LMStudioServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        # Quiz kaydı oluştur
        quiz = Quiz(
            title=f"{document.filename} Quiz",
            course_id=document.course_id,
            document_id=document.id
        )

        db.add(quiz)
        db.flush()

        # AI tarafından oluşturulan soruları kaydet
        questions = []

        for generated_question in generated_quiz.questions:
            question = Question(
                quiz_id=quiz.id,
                question_type=generated_question.question_type,
                question_text=generated_question.question_text,
                option_a=generated_question.option_a,
                option_b=generated_question.option_b,
                option_c=generated_question.option_c,
                option_d=generated_question.option_d,
                option_e=generated_question.option_e,
                correct_answer=generated_question.correct_answer,
                explanation=generated_question.explanation
            )

            db.add(question)
            questions.append(question)

        db.commit()
        db.refresh(quiz)

    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("Quiz database transaction failed")
        raise HTTPException(
            status_code=500,
            detail="Quiz veritabanına kaydedilemedi."
        ) from error

    return {
        "message": "Quiz başarıyla oluşturuldu.",
        "quiz_id": quiz.id,
        "title": quiz.title,
        "document_id": quiz.document_id,
        "question_count": len(questions),
        "questions": [
            {
                "id": question.id,
                "question_type": question.question_type,
                "context_text": generated_question.context_text,
                "question_text": question.question_text,
                "option_a": question.option_a,
                "option_b": question.option_b,
                "option_c": question.option_c,
                "option_d": question.option_d,
                "option_e": question.option_e,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation
            }
            for question, generated_question in zip(
                questions,
                generated_quiz.questions,
            )
        ]
    }


def _quiz_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/generate/stream")
def stream_quiz_generation(
    document_id: int,
    question_count: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(
            Document.id == document_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")

    if question_count < 1 or question_count > 20:
        raise HTTPException(
            status_code=400,
            detail="Soru sayısı 1 ile 20 arasında olmalıdır."
        )

    document_text = document.text
    document_filename = document.filename
    document_course_id = document.course_id
    previous_questions = _get_previous_document_questions(db, document.id)

    def event_stream():
        stream_db = SessionLocal()
        generated_questions = []
        logger.info(
            "Quiz stream started: document_id=%s requested=%s",
            document_id,
            question_count,
        )

        try:
            yield _quiz_sse_event(
                "status",
                {
                    "status": "started",
                    "requested_questions": question_count,
                },
            )

            for question in generate_quiz_questions_stream(
                document_text,
                question_count,
                previous_questions=previous_questions,
            ):
                generated_questions.append(question)
                question_index = len(generated_questions)
                question_data = question.model_dump()
                question_data["index"] = question_index
                yield _quiz_sse_event("question", question_data)
                logger.info("Question %s streamed", question_index)
                yield _quiz_sse_event(
                    "progress",
                    {
                        "completed_questions": question_index,
                        "total_questions": question_count,
                    },
                )

            if len(generated_questions) != question_count:
                raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

            quiz = Quiz(
                title=f"{document_filename} Quiz",
                course_id=document_course_id,
                document_id=document_id,
            )
            stream_db.add(quiz)
            stream_db.flush()

            for generated_question in generated_questions:
                stream_db.add(
                    Question(
                        quiz_id=quiz.id,
                        question_type=generated_question.question_type,
                        question_text=generated_question.question_text,
                        option_a=generated_question.option_a,
                        option_b=generated_question.option_b,
                        option_c=generated_question.option_c,
                        option_d=generated_question.option_d,
                        option_e=generated_question.option_e,
                        correct_answer=generated_question.correct_answer,
                        explanation=generated_question.explanation,
                    )
                )

            stream_db.commit()
            logger.info(
                "Quiz stream completed: questions=%s",
                len(generated_questions),
            )
            yield _quiz_sse_event(
                "done",
                {
                    "quiz_id": quiz.id,
                    "question_count": len(generated_questions),
                },
            )

        except Exception:
            stream_db.rollback()
            logger.exception(
                "Quiz stream failed: document_id=%s",
                document_id,
            )
            yield _quiz_sse_event(
                "error",
                {
                    "message": "Quiz tamamlanamadı, kayıt oluşturulmadı."
                },
            )

        finally:
            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =========================================================
# QUIZLERİ LİSTELE
# =========================================================

@router.get("/")
def get_quizzes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    quizzes = (
        db.query(
            Quiz,
            func.count(Question.id).label("question_count")
        )
        .join(Course, Quiz.course_id == Course.id)
        .outerjoin(Question, Question.quiz_id == Quiz.id)
        .filter(
            Course.user_id == current_user.id
        )
        .group_by(Quiz.id)
        .all()
    )

    return [
        {
            "id": quiz.id,
            "title": quiz.title,
            "course_id": quiz.course_id,
            "document_id": quiz.document_id,
            "created_at": quiz.created_at,
            "question_count": question_count
        }
        for quiz, question_count in quizzes
    ]


# =========================================================
# TEK BİR QUIZ GETİR
# =========================================================

@router.get("/{quiz_id}")
def get_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    quiz = _get_accessible_quiz(
    db,
    quiz_id,
    current_user,
)

    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı.")

    return {
        "id": quiz.id,
        "title": quiz.title,
        "course_id": quiz.course_id,
        "document_id": quiz.document_id,
        "created_at": quiz.created_at,
        "questions": [
            {
                "id": question.id,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "option_a": question.option_a,
                "option_b": question.option_b,
                "option_c": question.option_c,
                "option_d": question.option_d,
                "option_e": question.option_e
            }
            for question in quiz.questions
        ]
    }

# =========================================================
# QUIZ DELETE
# =========================================================

@router.delete("/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = _get_accessible_quiz(
        db,
        quiz_id,
        current_user,
    )

    if quiz is None:
        raise HTTPException(
            status_code=404,
            detail="Quiz bulunamadı."
        )

    try:
        db.delete(quiz)
        db.commit()

        return {
            "message": "Quiz başarıyla silindi.",
            "quiz_id": quiz_id
        }

    except SQLAlchemyError as error:
        db.rollback()
        logger.exception(
            "Quiz deletion failed: quiz_id=%s",
            quiz_id
        )
        raise HTTPException(
            status_code=500,
            detail="Quiz silinemedi."
        ) from error

# =========================================================
# QUIZ SUBMIT
# =========================================================

@router.post("/{quiz_id}/submit")
def submit_quiz(
    quiz_id: int,
    submission: QuizSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Quiz'i bul ve kullanıcının kendi quiz'i olduğunu kontrol et
    quiz = _get_accessible_quiz(
    db,
    quiz_id,
    current_user,
)

    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı.")

    # Quiz sorularını al
    questions = (
        db.query(Question)
        .filter(
            Question.quiz_id == quiz_id
        )
        .all()
    )

    # Kullanıcının cevaplarını dictionary haline getir
    user_answers = {
        answer.question_id: answer.answer
        for answer in submission.answers
    }

    correct_count = 0
    wrong_count = 0

    results = []

    # =====================================================
    # CEVAPLARI DEĞERLENDİR
    # =====================================================

    for question in questions:

        user_answer = user_answers.get(question.id)

        is_correct = _is_correct_multiple_choice(
            user_answer,
            question.correct_answer,
        )

        # -----------------------------------------------------
        # DOĞRU / YANLIŞ SAYISINI GÜNCELLE
        # -----------------------------------------------------

        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1

        # -----------------------------------------------------
        # SONUÇLARA EKLE
        # -----------------------------------------------------

        results.append({
            "question_id": question.id,
            "question_text": question.question_text,
            "user_answer": user_answer,
            "correct_answer": question.correct_answer,
            "is_correct": is_correct,
            "explanation": question.explanation
        })

    # =========================================================
    # PUAN HESAPLA
    # =========================================================

    total_questions = len(questions)

    if total_questions > 0:
        score = round(
            (correct_count / total_questions) * 100
        )
    else:
        score = 0

    # =========================================================
    # QUIZ ATTEMPT KAYDI
    # =========================================================

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        score=score,
        correct_count=correct_count,
        wrong_count=wrong_count,
        total_questions=total_questions
    )

    achievement_created = False

    try:
        db.add(attempt)

        update_goal_progress(
            db=db,
            user_id=current_user.id,
            goal_type="quiz_count",
            amount=1,
            commit=False,
        )

        existing_achievement = (
            db.query(Achievement)
            .filter(
                Achievement.user_id == current_user.id,
                Achievement.achievement_type == "first_quiz"
            )
            .first()
        )

        if existing_achievement is None:
            db.add(Achievement(
                user_id=current_user.id,
                achievement_type="first_quiz",
                title="İlk Quiz",
                description="İlk quizini başarıyla tamamladın!",
                completed=True
            ))
            achievement_created = True

        db.commit()
        db.refresh(attempt)
    except Exception as error:
        db.rollback()
        logger.exception("Quiz submit transaction failed: quiz_id=%s", quiz_id)
        raise HTTPException(
            status_code=500,
            detail="Quiz sonucu kaydedilemedi."
        ) from error

    # =========================================================
    # SONUÇ DÖNDÜR
    # =========================================================

    return {
        "message": "Quiz başarıyla tamamlandı.",
        "attempt_id": attempt.id,
        "quiz_id": quiz.id,
        "title": quiz.title,
        "total_questions": total_questions,
        "correct": correct_count,
        "wrong": wrong_count,
        "score": score,
        "achievement_created": achievement_created,
        "completed_at": attempt.completed_at,
        "results": results
    }


# =========================================================
# QUIZ DENEMELERİNİ GETİR
# =========================================================

@router.get("/{quiz_id}/attempts")
def get_quiz_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Quiz'i bul ve kullanıcının kendi quiz'i olduğunu kontrol et
    quiz = _get_accessible_quiz(
    db,
    quiz_id,
    current_user,
)

    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz bulunamadı.")

    # Quiz denemelerini getir
    attempts = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.quiz_id == quiz_id
        )
        .order_by(
            QuizAttempt.completed_at.desc()
        )
        .all()
    )

    return [
        {
            "id": attempt.id,
            "quiz_id": attempt.quiz_id,
            "score": attempt.score,
            "correct_count": attempt.correct_count,
            "wrong_count": attempt.wrong_count,
            "total_questions": attempt.total_questions,
            "completed_at": attempt.completed_at
        }
        for attempt in attempts
    ]
