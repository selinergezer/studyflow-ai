from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.goal import Goal
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user

from app.schemas.goal import (
    GoalCreate,
    GoalUpdate,
    GoalResponse
)

router = APIRouter(
    prefix="/goals",
    tags=["Goals"]
)


# =========================
# CREATE GOAL
# =========================

@router.post("/", response_model=GoalResponse)
def create_goal(
    goal_data: GoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Tarih kontrolü
    if goal_data.end_date < goal_data.start_date:
        return {
            "message": "Bitiş tarihi başlangıç tarihinden önce olamaz."
        }

    # Hedef türü kontrolü
    allowed_goal_types = [
        "study_time",
        "quiz_count",
        "flashcard_count",
        "document_count"
    ]

    if goal_data.goal_type not in allowed_goal_types:
        return {
            "message": (
                "Geçersiz goal_type. "
                "study_time, quiz_count, flashcard_count "
                "veya document_count olmalıdır."
            )
        }

    # Hedef değeri kontrolü
    if goal_data.target_value <= 0:
        return {
            "message": "target_value 0'dan büyük olmalıdır."
        }

    # Course seçilmişse kullanıcının dersi mi kontrol et
    if goal_data.course_id is not None:

        course = (
            db.query(Course)
            .filter(
                Course.id == goal_data.course_id,
                Course.user_id == current_user.id
            )
            .first()
        )

        if course is None:
            return {
                "message": "Ders bulunamadı."
            }

    # Goal oluştur
    goal = Goal(
        user_id=current_user.id,
        course_id=goal_data.course_id,
        title=goal_data.title,
        goal_type=goal_data.goal_type,
        target_value=goal_data.target_value,
        current_value=0,
        start_date=goal_data.start_date,
        end_date=goal_data.end_date,
        completed=False
    )

    db.add(goal)
    db.commit()
    db.refresh(goal)

    return goal


# =========================
# GET ALL GOALS
# =========================

@router.get("/", response_model=list[GoalResponse])
def get_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == current_user.id
        )
        .order_by(Goal.end_date.asc())
        .all()
    )

    return goals


# =========================
# GET SINGLE GOAL
# =========================

@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    goal = (
        db.query(Goal)
        .filter(
            Goal.id == goal_id,
            Goal.user_id == current_user.id
        )
        .first()
    )

    if goal is None:
        return {
            "message": "Hedef bulunamadı."
        }

    return goal


# =========================
# UPDATE GOAL
# =========================

@router.put("/{goal_id}", response_model=GoalResponse)
def update_goal(
    goal_id: int,
    goal_data: GoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    goal = (
        db.query(Goal)
        .filter(
            Goal.id == goal_id,
            Goal.user_id == current_user.id
        )
        .first()
    )

    if goal is None:
        return {
            "message": "Hedef bulunamadı."
        }

    # Güncellenecek alanları kontrol et
    if goal_data.title is not None:
        goal.title = goal_data.title

    if goal_data.goal_type is not None:

        allowed_goal_types = [
            "study_time",
            "quiz_count",
            "flashcard_count",
            "document_count"
        ]

        if goal_data.goal_type not in allowed_goal_types:
            return {
                "message": (
                    "Geçersiz goal_type. "
                    "study_time, quiz_count, flashcard_count "
                    "veya document_count olmalıdır."
                )
            }

        goal.goal_type = goal_data.goal_type

    if goal_data.target_value is not None:

        if goal_data.target_value <= 0:
            return {
                "message": "target_value 0'dan büyük olmalıdır."
            }

        goal.target_value = goal_data.target_value

    if goal_data.start_date is not None:
        goal.start_date = goal_data.start_date

    if goal_data.end_date is not None:
        goal.end_date = goal_data.end_date

    # Tarih kontrolü
    if goal.end_date < goal.start_date:
        return {
            "message": "Bitiş tarihi başlangıç tarihinden önce olamaz."
        }

    # Course güncellenecekse kontrol et
    if goal_data.course_id is not None:

        course = (
            db.query(Course)
            .filter(
                Course.id == goal_data.course_id,
                Course.user_id == current_user.id
            )
            .first()
        )

        if course is None:
            return {
                "message": "Ders bulunamadı."
            }

        goal.course_id = goal_data.course_id

    # Hedef tamamlandı mı?
    if goal.current_value >= goal.target_value:
        goal.completed = True
    else:
        goal.completed = False

    db.commit()
    db.refresh(goal)

    return goal


# =========================
# DELETE GOAL
# =========================

@router.delete("/{goal_id}")
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    goal = (
        db.query(Goal)
        .filter(
            Goal.id == goal_id,
            Goal.user_id == current_user.id
        )
        .first()
    )

    if goal is None:
        return {
            "message": "Hedef bulunamadı."
        }

    db.delete(goal)
    db.commit()

    return {
        "message": "Hedef başarıyla silindi."
    }