from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.goal import Goal


def update_goal_progress(
    db: Session,
    user_id: int,
    goal_type: str,
    amount: int = 1
):
    """
    Kullanıcının aktif hedeflerini günceller.

    goal_type:
    - quiz_count
    - flashcard_count
    - document_count
    - study_time
    """

    now = datetime.now(timezone.utc).date()

    goals = (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.goal_type == goal_type,
            Goal.completed == False,
            Goal.start_date <= now,
            Goal.end_date >= now
        )
        .all()
    )

    for goal in goals:

        goal.current_value += amount

        # Hedef değerini aşmasını engelle
        if goal.current_value >= goal.target_value:
            goal.current_value = goal.target_value
            goal.completed = True

    db.commit()