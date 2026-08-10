from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.database import get_db
from app.models.flashcard import Flashcard
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user

from app.models.document import Document
from app.services.ai_service import generate_flashcards

from datetime import datetime, timedelta, timezone

from app.schemas.flashcard import FlashcardReview

from app.services.goal_service import update_goal_progress


router = APIRouter(
    prefix="/flashcards",
    tags=["Flashcards"]
)


# =========================================================
# MANUEL FLASHCARD OLUŞTURMA
# =========================================================

@router.post("/")
def create_flashcard(
    course_id: int,
    question: str,
    answer: str,
    document_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if course is None:
        return {
            "message": "Course bulunamadı."
        }

    flashcard = Flashcard(
        question=question,
        answer=answer,
        course_id=course_id,
        document_id=document_id
    )

    db.add(flashcard)
    db.commit()
    db.refresh(flashcard)

    return {
        "message": "Flashcard başarıyla oluşturuldu.",
        "id": flashcard.id,
        "question": flashcard.question,
        "answer": flashcard.answer,
        "course_id": flashcard.course_id,
        "document_id": flashcard.document_id
    }


# =========================================================
# FLASHCARDLARI GETİR
# =========================================================

@router.get("/")
def get_flashcards(
    course_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = (
        db.query(Flashcard)
        .join(
            Course,
            Flashcard.course_id == Course.id
        )
        .filter(
            Course.user_id == current_user.id
        )
    )

    if course_id is not None:
        query = query.filter(
            Flashcard.course_id == course_id
        )

    flashcards = query.all()

    return [
        {
            "id": flashcard.id,
            "question": flashcard.question,
            "answer": flashcard.answer,
            "course_id": flashcard.course_id,
            "document_id": flashcard.document_id,
            "created_at": flashcard.created_at,
            "review_count": flashcard.review_count,
            "correct_count": flashcard.correct_count,
            "wrong_count": flashcard.wrong_count,
            "next_review": flashcard.next_review
        }
        for flashcard in flashcards
    ]


# =========================================================
# FLASHCARD SİL
# =========================================================

@router.delete("/{flashcard_id}")
def delete_flashcard(
    flashcard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    flashcard = (
        db.query(Flashcard)
        .join(
            Course,
            Flashcard.course_id == Course.id
        )
        .filter(
            Flashcard.id == flashcard_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if flashcard is None:
        return {
            "message": "Flashcard bulunamadı."
        }

    db.delete(flashcard)
    db.commit()

    return {
        "message": "Flashcard başarıyla silindi."
    }


# =========================================================
# AI FLASHCARD OLUŞTURMA
# =========================================================

@router.post("/generate")
def generate_flashcards_endpoint(
    course_id: int,
    document_id: int,
    flashcard_count: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Dokümanın kullanıcıya ait olup olmadığını kontrol et
    document = (
        db.query(Document)
        .join(
            Course,
            Document.course_id == Course.id
        )
        .filter(
            Document.id == document_id,
            Document.course_id == course_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        return {
            "message": "Doküman bulunamadı."
        }

    # PDF'den çıkarılmış metin var mı?
    if not document.text:
        return {
            "message": "Bu dokümanda işlenmiş metin bulunamadı."
        }

    # Flashcard sayısını sınırla
    if flashcard_count < 1 or flashcard_count > 30:
        return {
            "message": "Flashcard sayısı 1 ile 30 arasında olmalıdır."
        }

    # Gemini ile flashcard oluştur
    ai_result = generate_flashcards(
        document.text,
        flashcard_count
    )

    created_flashcards = []

    # Oluşturulan kartları veritabanına kaydet
    for item in ai_result.flashcards:

        flashcard = Flashcard(
            question=item.question,
            answer=item.answer,
            course_id=course_id,
            document_id=document_id
        )

        db.add(flashcard)
        db.flush()

        created_flashcards.append({
            "id": flashcard.id,
            "question": flashcard.question,
            "answer": flashcard.answer,
            "course_id": flashcard.course_id,
            "document_id": flashcard.document_id,
            "review_count": flashcard.review_count,
            "correct_count": flashcard.correct_count,
            "wrong_count": flashcard.wrong_count,
            "next_review": flashcard.next_review
        })

    db.commit()

    return {
        "message": "AI tarafından flashcard'lar başarıyla oluşturuldu.",
        "document_id": document_id,
        "course_id": course_id,
        "flashcard_count": len(created_flashcards),
        "flashcards": created_flashcards
    }


# =========================================================
# FLASHCARD DEĞERLENDİRME
# =========================================================

@router.post("/{flashcard_id}/review")
def review_flashcard(
    flashcard_id: int,
    review: FlashcardReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Flashcard'ın kullanıcıya ait olup olmadığını kontrol et
    flashcard = (
        db.query(Flashcard)
        .join(
            Course,
            Flashcard.course_id == Course.id
        )
        .filter(
            Flashcard.id == flashcard_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if flashcard is None:
        return {
            "message": "Flashcard bulunamadı."
        }

    # Sonucun geçerli olup olmadığını kontrol et
    if review.result not in ["easy", "hard", "forgot"]:
        return {
            "message": "Sonuç easy, hard veya forgot olmalıdır."
        }

    # Review sayısını artır
    flashcard.review_count += 1

    # =====================================================
    # EASY
    # =====================================================

    if review.result == "easy":

        flashcard.correct_count += 1

        # Kolay kart 3 gün sonra tekrar
        flashcard.next_review = (
            datetime.now(timezone.utc)
            + timedelta(days=3)
        )

    # =====================================================
    # HARD
    # =====================================================

    elif review.result == "hard":

        flashcard.correct_count += 1

        # Zor kart 1 gün sonra tekrar
        flashcard.next_review = (
            datetime.now(timezone.utc)
            + timedelta(days=1)
        )

    # =====================================================
    # FORGOT
    # =====================================================

    elif review.result == "forgot":

        flashcard.wrong_count += 1

        # Unutulan kart 2 saat sonra tekrar
        flashcard.next_review = (
            datetime.now(timezone.utc)
            + timedelta(hours=2)
        )

    db.commit()

# Flashcard tekrar hedefinin ilerlemesini güncelle
    update_goal_progress(
        db=db,
        user_id=current_user.id,
        goal_type="flashcard_count",
        amount=1
    )

    db.refresh(flashcard)



    return {
        "message": "Flashcard değerlendirmesi kaydedildi.",
        "flashcard_id": flashcard.id,
        "result": review.result,
        "review_count": flashcard.review_count,
        "correct_count": flashcard.correct_count,
        "wrong_count": flashcard.wrong_count,
        "next_review": flashcard.next_review
    }


# =========================================================
# TEKRAR ZAMANI GELEN FLASHCARDLAR
# =========================================================

@router.get("/review")
def get_flashcards_for_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    now = datetime.now(timezone.utc)

    flashcards = (
        db.query(Flashcard)
        .join(
            Course,
            Flashcard.course_id == Course.id
        )
        .filter(
            Course.user_id == current_user.id,
            or_(
                Flashcard.next_review.is_(None),
                Flashcard.next_review <= now
            )
        )
        .order_by(
            Flashcard.next_review.asc().nullsfirst()
        )
        .all()
    )

    return [
        {
            "id": flashcard.id,
            "question": flashcard.question,
            "answer": flashcard.answer,
            "course_id": flashcard.course_id,
            "document_id": flashcard.document_id,
            "review_count": flashcard.review_count,
            "correct_count": flashcard.correct_count,
            "wrong_count": flashcard.wrong_count,
            "next_review": flashcard.next_review
        }
        for flashcard in flashcards
    ]