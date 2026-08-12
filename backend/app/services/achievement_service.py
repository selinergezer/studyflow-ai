from sqlalchemy.orm import Session

from app.models.achievement import Achievement
from app.models.study_session import StudySession


def check_study_achievements(
    db: Session,
    user_id: int
):
    """
    Kullanıcının çalışma verilerine göre
    başarılarını kontrol eder ve eksik olanları oluşturur.
    """

    study_sessions = (
        db.query(StudySession)
        .filter(
            StudySession.user_id == user_id
        )
        .all()
    )

    total_minutes = sum(
        session.duration_minutes or 0
        for session in study_sessions
    )

    # ========================================================
    # İLK ÇALIŞMA
    # ========================================================

    if total_minutes > 0:

        existing = (
            db.query(Achievement)
            .filter(
                Achievement.user_id == user_id,
                Achievement.achievement_type == "first_study"
            )
            .first()
        )

        if existing is None:

            achievement = Achievement(
                user_id=user_id,
                achievement_type="first_study",
                title="İlk Çalışma",
                description="İlk çalışma oturumunu tamamladın.",
                completed=True
            )

            db.add(achievement)

    # ========================================================
    # 5 SAAT ÇALIŞMA
    # ========================================================

    if total_minutes >= 300:

        existing = (
            db.query(Achievement)
            .filter(
                Achievement.user_id == user_id,
                Achievement.achievement_type == "five_hours"
            )
            .first()
        )

        if existing is None:

            achievement = Achievement(
                user_id=user_id,
                achievement_type="five_hours",
                title="5 Saat Çalışma",
                description="Toplam 5 saat çalışma süresine ulaştın.",
                completed=True
            )

            db.add(achievement)