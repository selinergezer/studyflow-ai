from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.event import Event
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user


router = APIRouter(
    prefix="/events",
    tags=["Events"]
)


# ============================================================
# EVENT OLUŞTUR
# ============================================================

@router.post("/")
def create_event(
    title: str,
    event_type: str,
    start_date: datetime,
    end_date: Optional[datetime] = None,
    description: Optional[str] = None,
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------------------------
    # Course kontrolü
    # --------------------------------------------------------

    if course_id is not None:

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
                detail="Ders bulunamadı."
            )

    # --------------------------------------------------------
    # Event type kontrolü
    # --------------------------------------------------------

    allowed_types = [
        "exam",
        "assignment",
        "project",
        "study"
    ]

    if event_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=(
                "event_type exam, assignment, "
                "project veya study olmalıdır."
            )
        )

    # --------------------------------------------------------
    # Tarih kontrolü
    # --------------------------------------------------------

    if end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date, start_date tarihinden önce olamaz."
        )

    # --------------------------------------------------------
    # Event oluştur
    # --------------------------------------------------------

    event = Event(
        user_id=current_user.id,
        course_id=course_id,
        title=title,
        description=description,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        completed=False
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "message": "Event başarıyla oluşturuldu.",
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "event_type": event.event_type,
        "course_id": event.course_id,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "completed": event.completed
    }


# ============================================================
# EVENTLERİ LİSTELE
# ============================================================

@router.get("/")
def get_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    events = (
        db.query(Event)
        .filter(
            Event.user_id == current_user.id
        )
        .order_by(
            Event.start_date.asc()
        )
        .all()
    )

    return [
        {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "event_type": event.event_type,
            "course_id": event.course_id,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "completed": event.completed
        }
        for event in events
    ]


# ============================================================
# TEK EVENT GETİR
# ============================================================

@router.get("/{event_id}")
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    event = (
        db.query(Event)
        .filter(
            Event.id == event_id,
            Event.user_id == current_user.id
        )
        .first()
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event bulunamadı."
        )

    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "event_type": event.event_type,
        "course_id": event.course_id,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "completed": event.completed
    }


# ============================================================
# EVENT GÜNCELLE
# ============================================================

@router.put("/{event_id}")
def update_event(
    event_id: int,
    title: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    description: Optional[str] = None,
    completed: Optional[bool] = None,
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    event = (
        db.query(Event)
        .filter(
            Event.id == event_id,
            Event.user_id == current_user.id
        )
        .first()
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event bulunamadı."
        )

    # --------------------------------------------------------
    # Event type kontrolü
    # --------------------------------------------------------

    if event_type is not None:

        allowed_types = [
            "exam",
            "assignment",
            "project",
            "study"
        ]

        if event_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=(
                    "event_type exam, assignment, "
                    "project veya study olmalıdır."
                )
            )

        event.event_type = event_type

    # --------------------------------------------------------
    # Course kontrolü
    # --------------------------------------------------------

    if course_id is not None:

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
                detail="Ders bulunamadı."
            )

        event.course_id = course_id

    # --------------------------------------------------------
    # Alanları güncelle
    # --------------------------------------------------------

    if title is not None:
        event.title = title

    if description is not None:
        event.description = description

    if start_date is not None:
        event.start_date = start_date

    if end_date is not None:
        event.end_date = end_date

    if (
        event.end_date is not None
        and event.end_date < event.start_date
    ):
        raise HTTPException(
            status_code=400,
            detail="end_date, start_date tarihinden önce olamaz."
        )

    if completed is not None:
        event.completed = completed

    db.commit()
    db.refresh(event)

    return {
        "message": "Event başarıyla güncellendi.",
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "event_type": event.event_type,
        "course_id": event.course_id,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "completed": event.completed
    }


# ============================================================
# EVENT SİL
# ============================================================

@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    event = (
        db.query(Event)
        .filter(
            Event.id == event_id,
            Event.user_id == current_user.id
        )
        .first()
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event bulunamadı."
        )

    db.delete(event)
    db.commit()

    return {
        "message": "Event başarıyla silindi."
    }