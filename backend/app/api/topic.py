from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.topic import Topic
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user

router = APIRouter(
    prefix="/topics",
    tags=["Topics"]
)


@router.post("/")
def create_topic(
    course_id: int,
    name: str,
    description: str | None = None,
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
            status_code=404,
            detail="Ders bulunamadı."
        )

    topic = Topic(
        course_id=course_id,
        name=name,
        description=description
    )

    db.add(topic)
    db.commit()
    db.refresh(topic)

    return topic

@router.get("/")
def get_topics(
    course_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = (
        db.query(Topic)
        .join(Course)
        .filter(
            Course.user_id == current_user.id
        )
    )

    if course_id is not None:
        query = query.filter(
            Topic.course_id == course_id
        )

    topics = query.order_by(
        Topic.id.asc()
    ).all()

    return topics

@router.get("/{topic_id}")
def get_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    topic = (
        db.query(Topic)
        .join(Course)
        .filter(
            Topic.id == topic_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if topic is None:
        raise HTTPException(
            status_code=404,
            detail="Konu bulunamadı."
        )

    return topic
@router.put("/{topic_id}")
def update_topic(
    topic_id: int,
    name: str | None = None,
    description: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    topic = (
        db.query(Topic)
        .join(Course)
        .filter(
            Topic.id == topic_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if topic is None:
        raise HTTPException(
            status_code=404,
            detail="Konu bulunamadı."
        )

    if name is not None:
        topic.name = name

    if description is not None:
        topic.description = description

    db.commit()
    db.refresh(topic)

    return topic

@router.delete("/{topic_id}")
def delete_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    topic = (
        db.query(Topic)
        .join(Course)
        .filter(
            Topic.id == topic_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if topic is None:
        raise HTTPException(
            status_code=404,
            detail="Konu bulunamadı."
        )

    db.delete(topic)
    db.commit()

    return {
        "message": "Konu başarıyla silindi."
    }