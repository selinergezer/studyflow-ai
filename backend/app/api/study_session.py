from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.study_session import StudySession
from app.models.course import Course
from app.models.user import User

from app.schemas.study_session import (
    StudySessionCreate,
    StudySessionUpdate,
    StudySessionResponse
)

from app.core.security import get_current_user


router = APIRouter(
    prefix="/study-sessions",
    tags=["Study Sessions"]
)


# ============================================================
# ÇALIŞMA OTURUMU OLUŞTUR
# ============================================================

@router.post(
    "/",
    response_model=StudySessionResponse
)
def create_study_session(
    session_data: StudySessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Ders kullanıcının kendi dersi mi?
    course = (
        db.query(Course)
        .filter(
            Course.id == session_data.course_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Ders bulunamadı."
        )

    # Süre kontrolü
    if session_data.duration_minutes <= 0:
        raise HTTPException(
            status_code=400,
            detail="Çalışma süresi 0'dan büyük olmalıdır."
        )

    # Çalışma oturumu oluştur
    study_session = StudySession(
        user_id=current_user.id,
        course_id=session_data.course_id,
        study_date=session_data.study_date,
        duration_minutes=session_data.duration_minutes,
        description=session_data.description
    )

    db.add(study_session)
    db.commit()
    db.refresh(study_session)

    return study_session


# ============================================================
# TÜM ÇALIŞMA OTURUMLARINI GETİR
# ============================================================

@router.get(
    "/",
    response_model=list[StudySessionResponse]
)
def get_study_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    sessions = (
        db.query(StudySession)
        .filter(
            StudySession.user_id == current_user.id
        )
        .order_by(
            StudySession.study_date.desc()
        )
        .all()
    )

    return sessions


# ============================================================
# TEK ÇALIŞMA OTURUMU GETİR
# ============================================================

@router.get(
    "/{session_id}",
    response_model=StudySessionResponse
)
def get_study_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == session_id,
            StudySession.user_id == current_user.id
        )
        .first()
    )

    if study_session is None:
        raise HTTPException(
            status_code=404,
            detail="Çalışma kaydı bulunamadı."
        )

    return study_session


# ============================================================
# ÇALIŞMA OTURUMU GÜNCELLE
# ============================================================

@router.put(
    "/{session_id}",
    response_model=StudySessionResponse
)
def update_study_session(
    session_id: int,
    session_data: StudySessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == session_id,
            StudySession.user_id == current_user.id
        )
        .first()
    )

    if study_session is None:
        raise HTTPException(
            status_code=404,
            detail="Çalışma kaydı bulunamadı."
        )

    # Ders değiştiriliyorsa kullanıcının dersi mi?
    if session_data.course_id is not None:

        course = (
            db.query(Course)
            .filter(
                Course.id == session_data.course_id,
                Course.user_id == current_user.id
            )
            .first()
        )

        if course is None:
            raise HTTPException(
                status_code=404,
                detail="Ders bulunamadı."
            )

        study_session.course_id = session_data.course_id

    if session_data.study_date is not None:
        study_session.study_date = session_data.study_date

    if session_data.duration_minutes is not None:

        if session_data.duration_minutes <= 0:
            raise HTTPException(
                status_code=400,
                detail="Çalışma süresi 0'dan büyük olmalıdır."
            )

        study_session.duration_minutes = (
            session_data.duration_minutes
        )

    if session_data.description is not None:
        study_session.description = session_data.description

    db.commit()
    db.refresh(study_session)

    return study_session


# ============================================================
# ÇALIŞMA OTURUMU SİL
# ============================================================

@router.delete("/{session_id}")
def delete_study_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == session_id,
            StudySession.user_id == current_user.id
        )
        .first()
    )

    if study_session is None:
        raise HTTPException(
            status_code=404,
            detail="Çalışma kaydı bulunamadı."
        )

    db.delete(study_session)
    db.commit()

    return {
        "message": "Çalışma kaydı başarıyla silindi."
    }