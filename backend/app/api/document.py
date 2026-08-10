import os
import shutil

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user

from app.services.pdf_service import extract_text_from_pdf
from app.services.ai_service import generate_summary


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


# =========================================================
# PDF YÜKLE
# =========================================================

@router.post("/upload")
def upload_document(
    course_id: int,
    file: UploadFile = File(...),
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
        raise HTTPException(
            status_code=404,
            detail="Course bulunamadı."
        )

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text, page_count = extract_text_from_pdf(file_path)

    summary = generate_summary(text)

    new_document = Document(
        filename=file.filename,
        file_path=file_path,
        text=text,
        summary=summary,
        page_count=page_count,
        course_id=course_id
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return {
        "message": "PDF başarıyla yüklendi.",
        "document_id": new_document.id,
        "filename": new_document.filename,
        "page_count": new_document.page_count,
        "summary": new_document.summary
    }


# =========================================================
# KULLANICININ TÜM PDF'LERİNİ GETİR
# =========================================================

@router.get("/")
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    documents = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    return documents


# =========================================================
# TEK BİR PDF'Yİ GETİR
# =========================================================

@router.get("/{document_id}")
def get_document(
    document_id: int,
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
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    return document


# =========================================================
# PDF SİL
# =========================================================

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
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
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    # Fiziksel PDF dosyasını sil
    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    # Veritabanından sil
    db.delete(document)
    db.commit()

    return {
        "message": "Document başarıyla silindi.",
        "document_id": document_id
    }