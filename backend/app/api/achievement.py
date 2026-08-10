from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.achievement import Achievement
from app.models.user import User
from app.core.security import get_current_user


router = APIRouter(
    prefix="/achievements",
    tags=["Achievements"]
)


# =========================
# BAŞARILARI LİSTELE
# =========================

@router.get("/")
def get_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    achievements = (
        db.query(Achievement)
        .filter(
            Achievement.user_id == current_user.id
        )
        .all()
    )

    return [
        {
            "id": achievement.id,
            "achievement_type": achievement.achievement_type,
            "title": achievement.title,
            "description": achievement.description,
            "completed": achievement.completed
        }
        for achievement in achievements
    ]


# =========================
# BAŞARI OLUŞTUR
# =========================

@router.post("/")
def create_achievement(
    achievement_type: str,
    title: str,
    description: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    achievement = Achievement(
        user_id=current_user.id,
        achievement_type=achievement_type,
        title=title,
        description=description,
        completed=True
    )

    db.add(achievement)
    db.commit()
    db.refresh(achievement)

    return {
        "message": "Başarı oluşturuldu.",
        "id": achievement.id,
        "achievement_type": achievement.achievement_type,
        "title": achievement.title,
        "description": achievement.description,
        "completed": achievement.completed
    }


# =========================
# BAŞARI SİL
# =========================

@router.delete("/{achievement_id}")
def delete_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    achievement = (
        db.query(Achievement)
        .filter(
            Achievement.id == achievement_id,
            Achievement.user_id == current_user.id
        )
        .first()
    )

    if achievement is None:
        return {
            "message": "Başarı bulunamadı."
        }

    db.delete(achievement)
    db.commit()

    return {
        "message": "Başarı başarıyla silindi."
    }