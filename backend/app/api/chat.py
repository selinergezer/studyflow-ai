from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db

from app.models.document import Document
from app.models.course import Course
from app.models.user import User

from app.core.security import get_current_user

from app.services.ai_service import ask_ai_about_document


router = APIRouter(
    prefix="/chat",
    tags=["AI Chat"]
)


class ChatRequest(BaseModel):
    document_id: int
    question: str


@router.post("/")
def chat_with_document(
    chat_data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # =========================================================
    # DOCUMENT KONTROLÜ
    # =========================================================

    document = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(
            Document.id == chat_data.document_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    # =========================================================
    # SORU KONTROLÜ
    # =========================================================

    if not chat_data.question.strip():

        raise HTTPException(
            status_code=400,
            detail="Soru boş olamaz."
        )

    # =========================================================
    # AI CEVABI
    # =========================================================

    answer = ask_ai_about_document(
        document.text,
        chat_data.question
    )

    return {
        "document_id": document.id,
        "question": chat_data.question,
        "answer": answer
    }