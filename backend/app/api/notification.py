from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.core.security import get_current_user


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


# ============================================================
# BİLDİRİMLERİ LİSTELE
# ============================================================

@router.get("/")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notifications = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id
        )
        .order_by(
            Notification.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "is_read": notification.is_read,
            "created_at": notification.created_at
        }
        for notification in notifications
    ]


# ============================================================
# OKUNMAMIŞ BİLDİRİM SAYISI
# ============================================================

@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
        .count()
    )

    return {
        "unread_count": count
    }


# ============================================================
# BİLDİRİMİ OKUNDU YAP
# ============================================================

@router.put("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Bildirim bulunamadı."
        )

    notification.is_read = True

    db.commit()
    db.refresh(notification)

    return {
        "message": "Bildirim okundu olarak işaretlendi.",
        "id": notification.id,
        "is_read": notification.is_read
    }


# ============================================================
# BİLDİRİM SİL
# ============================================================

@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Bildirim bulunamadı."
        )

    db.delete(notification)
    db.commit()

    return {
        "message": "Bildirim başarıyla silindi."
    }