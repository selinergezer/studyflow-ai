from fastapi import APIRouter, Depends
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