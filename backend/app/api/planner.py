from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.database import get_db

from app.models.course import Course
from app.models.event import Event
from app.models.goal import Goal
from app.models.user import User

from app.core.security import get_current_user

from app.schemas.planner import (
    PlannerRequest,
    PlannerResponse
)

from app.services.ai_service import generate_study_plan


router = APIRouter(
    prefix="/ai/planner",
    tags=["AI Planner"]
)


# =========================================================
# AI ÇALIŞMA PLANI OLUŞTUR
# =========================================================

@router.post(
    "/",
    response_model=PlannerResponse
)
def create_study_plan(
    request: PlannerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # -----------------------------------------------------
    # KULLANICININ DERSLERİNİ GETİR
    # -----------------------------------------------------

    courses = (
        db.query(Course)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    # -----------------------------------------------------
    # YAKLAŞAN EVENTLERİ GETİR
    # -----------------------------------------------------

    now = datetime.now(timezone.utc)

    events = (
        db.query(Event)
        .filter(
            Event.user_id == current_user.id,
            Event.completed == False,
            Event.start_date >= now
        )
        .order_by(
            Event.start_date.asc()
        )
        .limit(20)
        .all()
    )

    # -----------------------------------------------------
    # AKTİF HEDEFLERİ GETİR
    # -----------------------------------------------------

    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == current_user.id,
            Goal.completed == False
        )
        .order_by(
            Goal.end_date.asc()
        )
        .limit(20)
        .all()
    )

    # -----------------------------------------------------
    # HAFTALIK ÇALIŞMA HEDEFİNİ BUL
    # -----------------------------------------------------

    weekly_hours_target = None

    for goal in goals:
        if goal.goal_type == "study_time":
            weekly_hours_target = goal.target_value
            break

    # -----------------------------------------------------
    # ÇALIŞMA HEDEFİ YOKSA MAKSİMUM KAPASİTEYİ KULLAN
    # -----------------------------------------------------

    if weekly_hours_target is None:
        weekly_hours_target = request.available_hours_per_day * 7

    # -----------------------------------------------------
    # AI PLAN OLUŞTUR
    # -----------------------------------------------------

    result = generate_study_plan(
        courses=courses,
        events=events,
        goals=goals,
        available_hours_per_day=request.available_hours_per_day,
        target_gpa=request.target_gpa,
        weekly_hours_target=weekly_hours_target
    )

    return result