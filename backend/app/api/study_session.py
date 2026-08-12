from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.study_session import StudySession
from app.models.course import Course
from app.models.goal import Goal
from app.models.user import User
from app.services.achievement_service import check_study_achievements

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
# STUDY TIME HEDEFLERİNİ GÜNCELLE
# ============================================================

def update_study_time_goals(
    db: Session,
    user_id: int
):
    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.goal_type == "study_time"
        )
        .all()
    )

    for goal in goals:

        query = (
            db.query(StudySession)
            .filter(
                StudySession.user_id == user_id,
                StudySession.study_date >= goal.start_date,
                StudySession.study_date <= goal.end_date
            )
        )

        # Hedef belirli bir derse aitse
        if goal.course_id is not None:
            query = query.filter(
                StudySession.course_id == goal.course_id
            )

        sessions = query.all()

        total_minutes = sum(
            session.duration_minutes
            for session in sessions
        )

        # study_time hedefini saat olarak tutuyoruz
        total_hours = round(
            total_minutes / 60,
            2
        )

        goal.current_value = total_hours

        if goal.current_value >= goal.target_value:
            goal.completed = True
        else:
            goal.completed = False


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

    # Kullanıcının kendi dersi mi?
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
    db.flush()

# Study time hedeflerini güncelle
    update_study_time_goals(
    db,
    current_user.id
    )

# Çalışma başarılarını kontrol et
    check_study_achievements(
    db,
    current_user.id
    )

    db.commit()
    db.refresh(study_session)

    return study_session


# ============================================================
# TÜM ÇALIŞMA OTURUMLARI
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
# TEK ÇALIŞMA OTURUMU
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

    # Güncel çalışma kayıtlarına göre hedefleri yeniden hesapla
    update_study_time_goals(
        db,
        current_user.id
    )

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
    db.flush()

    # Kayıt silindikten sonra hedefleri yeniden hesapla
    update_study_time_goals(
        db,
        current_user.id
    )

    db.commit()

    return {
        "message": "Çalışma kaydı başarıyla silindi."
    }