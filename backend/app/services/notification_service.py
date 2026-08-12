from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User

def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False
    )

    db.add(notification)
    db.flush()

    return notification