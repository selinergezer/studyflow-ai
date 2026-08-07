import os
import shutil

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user

from app.services.pdf_service import extract_text_from_pdf

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

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
        return {
            "message": "Course bulunamadı."
        }

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text, page_count = extract_text_from_pdf(file_path)

    new_document = Document(
    filename=file.filename,
    file_path=file_path,
    text=text,
    page_count=page_count,
    summary=None,
    course_id=course_id
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return {
        "message": "PDF başarıyla yüklendi.",
        "document_id": new_document.id,
        "filename": new_document.filename
    }