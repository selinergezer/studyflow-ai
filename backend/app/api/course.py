import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.course import Course
from app.models.user import User
from app.schemas.course import CourseCreate, CourseResponse
from app.core.security import get_current_user

from typing import List


router = APIRouter(
    prefix="/courses",
    tags=["Courses"]
)


@router.post("/", response_model=CourseResponse)
def create_course(
    course: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_course = Course(
        name=course.name,
        description=course.description,
        user_id=current_user.id
    )

    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    return new_course


@router.get("/", response_model=List[CourseResponse])
def get_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    courses = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    return courses


@router.delete(
    "/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_course(
    course_id: int,
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

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )

    # Kursa bağlı fiziksel dosyaların yollarını
    # kurs silinmeden önce alıyoruz.
    document_paths = [
        document.file_path
        for document in course.documents
        if document.file_path
    ]

    # Kursu ve SQLAlchemy cascade ilişkilerini sil.
    db.delete(course)
    db.commit()

    # DB işlemi başarılı olduktan sonra fiziksel dosyaları temizle.
    for file_path in document_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            # Fiziksel dosya silinemese bile
            # veritabanı işlemi başarılı kalır.
            pass