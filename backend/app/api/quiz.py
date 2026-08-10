from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.quiz import Quiz
from app.models.question import Question
from app.models.document import Document
from app.models.course import Course
from app.models.user import User

from app.core.security import get_current_user
from app.services.ai_service import generate_quiz

from app.schemas.quiz import QuizSubmit
from app.models.quiz_attempt import QuizAttempt

from app.services.goal_service import update_goal_progress

router = APIRouter(
    prefix="/quizzes",
    tags=["Quizzes"]
)


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

    # PDF'deki metinden AI ile quiz oluştur
    generated_quiz = generate_quiz(
        document.text,
        question_count
    )

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
            correct_answer=generated_question.correct_answer,
            explanation=generated_question.explanation
        )

        db.add(question)
        questions.append(question)

    db.commit()

    db.refresh(quiz)

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
                "question_text": question.question_text,
                "option_a": question.option_a,
                "option_b": question.option_b,
                "option_c": question.option_c,
                "option_d": question.option_d,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation
            }
            for question in questions
        ]
    }

@router.get("/")
def get_quizzes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quizzes = (
        db.query(Quiz)
        .join(Course, Quiz.course_id == Course.id)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    return [
        {
            "id": quiz.id,
            "title": quiz.title,
            "course_id": quiz.course_id,
            "document_id": quiz.document_id,
            "created_at": quiz.created_at
        }
        for quiz in quizzes
    ]

@router.get("/{quiz_id}")
def get_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = (
        db.query(Quiz)
        .join(Course, Quiz.course_id == Course.id)
        .filter(
            Quiz.id == quiz_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if quiz is None:
        return {
            "message": "Quiz bulunamadı."
        }

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
                "option_d": question.option_d
            }
            for question in quiz.questions
        ]
    }

@router.post("/{quiz_id}/submit")
def submit_quiz(
    quiz_id: int,
    submission: QuizSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Quiz'i bul ve kullanıcının kendi quiz'i olduğunu kontrol et
    quiz = (
        db.query(Quiz)
        .join(Course, Quiz.course_id == Course.id)
        .filter(
            Quiz.id == quiz_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if quiz is None:
        return {
            "message": "Quiz bulunamadı."
        }

    # Quiz sorularını al
    questions = (
        db.query(Question)
        .filter(Question.quiz_id == quiz_id)
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

    for question in questions:

        user_answer = user_answers.get(question.id)

        is_correct = (
            user_answer is not None
            and user_answer.strip().lower()
            == question.correct_answer.strip().lower()
        )

        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1

        results.append({
            "question_id": question.id,
            "question_text": question.question_text,
            "user_answer": user_answer,
            "correct_answer": question.correct_answer,
            "is_correct": is_correct,
            "explanation": question.explanation
        })

    total_questions = len(questions)

    if total_questions > 0:
        score = round(
            (correct_count / total_questions) * 100
        )
    else:
        score = 0

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        score=score,
        correct_count=correct_count,
        wrong_count=wrong_count,
        total_questions=total_questions
    )

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    update_goal_progress(
        db=db,
        user_id=current_user.id,
        goal_type="quiz_count",
        amount=1
    )

    return {
    "message": "Quiz başarıyla tamamlandı.",
    "attempt_id": attempt.id,
    "quiz_id": quiz.id,
    "title": quiz.title,
    "total_questions": total_questions,
    "correct": correct_count,
    "wrong": wrong_count,
    "score": score,
    "completed_at": attempt.completed_at,
    "results": results
}

@router.get("/{quiz_id}/attempts")
def get_quiz_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = (
        db.query(Quiz)
        .join(Course, Quiz.course_id == Course.id)
        .filter(
            Quiz.id == quiz_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if quiz is None:
        return {
            "message": "Quiz bulunamadı."
        }

    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.quiz_id == quiz_id)
        .order_by(QuizAttempt.completed_at.desc())
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