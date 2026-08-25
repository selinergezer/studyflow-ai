from enum import member
import secrets
import string
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db

from app.models.course import Course
from app.models.study_room import StudyRoom
from app.models.user import User

from app.models.document import Document
from app.models.quiz import Quiz
from app.models.flashcard import Flashcard

from app.schemas.study_room import (
    StudyRoomCreate,
    StudyRoomJoin,
    StudyRoomResponse,
    StudyRoomMemberResponse,
    StudyRoomStatusUpdate,
)

from app.schemas.study_room_message import (
    StudyRoomMessageCreate,
    StudyRoomMessageResponse,
)

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.study_room_member import StudyRoomMember
from app.models.study_session import StudySession
from app.models.study_room_message import StudyRoomMessage

router = APIRouter(
    prefix="/study-rooms",
    tags=["Study Rooms"]
)


def generate_room_code(length: int = 6) -> str:
    characters = string.ascii_uppercase + string.digits

    return "".join(
        secrets.choice(characters)
        for _ in range(length)
    )


# ============================================================
# STUDY ROOM OLUÅTUR
# ============================================================

@router.post(
    "/",
    response_model=StudyRoomResponse
)
def create_study_room(
    room_data: StudyRoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # KullanÄ±cÄ±nÄ±n bu derse sahip olup olmadÄ±ÄŸÄ±nÄ± kontrol et
    course = (
        db.query(Course)
        .filter(
            Course.id == room_data.course_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Ders bulunamadÄ±."
        )

    # Benzersiz oda kodu oluÅŸtur
    while True:
        code = generate_room_code()

        existing_room = (
            db.query(StudyRoom)
            .filter(StudyRoom.code == code)
            .first()
        )

        if existing_room is None:
            break

    study_room = StudyRoom(
    name=room_data.name,
    code=code,
    course_id=room_data.course_id,
    created_by=current_user.id,
    is_active=True
)

    db.add(study_room)
    db.flush()

    member = StudyRoomMember(
    room_id=study_room.id,
    user_id=current_user.id,
    is_active=True,
    status="idle"
)

    db.add(member)

    db.commit()
    db.refresh(study_room)

    return study_room

# ============================================================
# STUDY ROOM SİL
# ============================================================

@router.delete(
    "/{room_id}",
)
def delete_study_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True,
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya zaten silinmiş.",
        )

    # Sadece oda sahibi silebilir
    if study_room.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'u silme yetkiniz yok.",
        )

    # Odayı soft delete yap
    study_room.is_active = False

    # Odadaki aktif üyelikleri kapat
    db.query(StudyRoomMember).filter(
        StudyRoomMember.room_id == room_id,
        StudyRoomMember.is_active == True,
    ).update(
        {
            StudyRoomMember.is_active: False,
            StudyRoomMember.status: "offline",
            StudyRoomMember.study_started_at: None,
        },
        synchronize_session=False,
    )

    db.commit()

    return {
        "message": "Study Room başarıyla silindi.",
        "room_id": room_id,
    }


# ============================================================
# KULLANICININ ODALARINI GETÄ°R
# ============================================================

# ============================================================
# KULLANICININ AKTİF OLDUĞU STUDY ROOM'LAR
# ============================================================

@router.get(
    "/",
    response_model=list[StudyRoomResponse]
)
def get_my_study_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rooms = (
        db.query(StudyRoom)
        .join(
            StudyRoomMember,
            StudyRoomMember.room_id == StudyRoom.id
        )
        .filter(
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True,
            StudyRoom.is_active == True,
        )
        .order_by(
            StudyRoom.created_at.desc()
        )
        .all()
    )

    return rooms

# ============================================================
# STUDY ROOM'A KATIL
# ============================================================

@router.post(
    "/join",
    response_model=StudyRoomResponse
)
def join_study_room(
    room_data: StudyRoomJoin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # OdayÄ± koduyla bul
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.code == room_data.code,
            StudyRoom.is_active == True
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadÄ± veya aktif deÄŸil."
        )

    # KullanÄ±cÄ± zaten bu odada mÄ±?
    existing_member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == study_room.id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if existing_member is not None:
        raise HTTPException(
            status_code=400,
            detail="Bu Study Room'a zaten Ã¼yesiniz."
        )

    # Daha Ã¶nce katÄ±lmÄ±ÅŸ ama ayrÄ±lmÄ±ÅŸsa mevcut kaydÄ± tekrar aktif et
    inactive_member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == study_room.id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == False
        )
        .first()
    )

    if inactive_member is not None:
        inactive_member.is_active = True
        inactive_member.status = "idle"

    else:
        member = StudyRoomMember(
            room_id=study_room.id,
            user_id=current_user.id,
            is_active=True,
            status="idle"
        )

        db.add(member)

    db.commit()
    db.refresh(study_room)

    return study_room

# ============================================================
# STUDY ROOM ÜYELERİNİ GETİR
# ============================================================

@router.get(
    "/{room_id}/members",
    response_model=list[StudyRoomMemberResponse]
)
def get_study_room_members(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya aktif değil."
        )

    # Kullanıcının bu odanın üyesi olup olmadığını kontrol et
    current_member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if current_member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz."
        )

    # Aktif üyeleri getir
    members = (
        db.query(StudyRoomMember, User)
        .join(
            User,
            StudyRoomMember.user_id == User.id
        )
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.is_active == True
        )
        .all()
    )

    return [
    StudyRoomMemberResponse(
        user_id=member.user_id,
        username=user.username,
        status=member.status,
        joined_at=member.joined_at,
        study_started_at=member.study_started_at
    )
    for member, user in members
]

# ============================================================
# STUDY ROOM STATUS GÜNCELLE
# ============================================================

@router.patch(
    "/{room_id}/status"
)
def update_study_room_status(
    room_id: int,
    status_data: StudyRoomStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Oda var mı?
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya aktif değil."
        )

    # Kullanıcı bu odanın aktif üyesi mi?
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz."
        )

    # Status güncelle
    member.status = status_data.status

    db.commit()
    db.refresh(member)

    return {
        "message": "Çalışma durumu güncellendi.",
        "status": member.status
    }
# ============================================================
# STUDY ROOM'DAN AYRIL
# ============================================================

@router.post(
    "/{room_id}/leave"
)
def leave_study_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Oda var mı?
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı."
        )

    # Kullanıcının aktif üyeliğini bul
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=400,
            detail="Bu Study Room'da aktif üye değilsiniz."
        )

    # Üyeliği kapat
    member.is_active = False
    member.status = "offline"

    db.commit()

    return {
        "message": "Study Room'dan başarıyla ayrıldınız.",
        "room_id": room_id,
        "status": member.status
    }

# ============================================================
# STUDY ROOM'DA ÇALIŞMAYA BAŞLA
# ============================================================

@router.post(
    "/{room_id}/start"
)
def start_study_session(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya aktif değil."
        )

    # Kullanıcının aktif üyeliğini bul
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz."
        )

    # Zaten çalışıyor mu?
    if member.status == "studying":
        raise HTTPException(
            status_code=400,
            detail="Zaten çalışıyorsunuz."
        )

    # Çalışmayı başlat
    member.status = "studying"
    member.study_started_at = datetime.utcnow()

    db.commit()
    db.refresh(member)

    return {
        "message": "Çalışma başladı.",
        "room_id": room_id,
        "status": member.status,
        "study_started_at": member.study_started_at
    }

# ============================================================
# STUDY ROOM'DA ÇALIŞMAYI BİTİR
# ============================================================

@router.post(
    "/{room_id}/finish"
)
def finish_study_session(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı."
        )

    # Aktif üyeliği bul
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz."
        )

    # Gerçekten çalışıyor mu?
    if member.status != "studying":
        raise HTTPException(
            status_code=400,
            detail="Şu anda aktif bir çalışma oturumunuz yok."
        )

    # Başlangıç zamanı var mı?
    if member.study_started_at is None:
        raise HTTPException(
            status_code=400,
            detail="Çalışma başlangıç zamanı bulunamadı."
        )

    # Geçen süreyi hesapla
    now = datetime.utcnow()

    elapsed_seconds = (
        now - member.study_started_at
    ).total_seconds()

    duration_minutes = max(
        1,
        round(elapsed_seconds / 60)
    )

    # StudySession oluştur
    study_session = StudySession(
        user_id=current_user.id,
        course_id=study_room.course_id,
        room_id=room_id,
        study_date=now.date(),
        duration_minutes=duration_minutes,
        description=f"Study Room: {study_room.name}"
    )

    db.add(study_session)

    # Üyenin durumunu güncelle
    member.status = "idle"
    member.study_started_at = None

    db.commit()
    db.refresh(study_session)

    return {
        "message": "Çalışma tamamlandı.",
        "room_id": room_id,
        "duration_minutes": duration_minutes,
        "status": member.status,
        "study_session_id": study_session.id
    }

# ============================================================
# STUDY ROOM İSTATİSTİKLERİ
# ============================================================

@router.get(
    "/{room_id}/stats"
)
def get_study_room_stats(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı."
        )

    # Kullanıcı bu odanın üyesi mi?
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz."
        )

    # Odanın toplam çalışma süresi
    total_minutes = (
        db.query(StudySession)
        .filter(
            StudySession.room_id == room_id
        )
        .with_entities(
            func.coalesce(
                func.sum(StudySession.duration_minutes),
                0
            )
        )
        .scalar()
    )

    # Bugünkü çalışma süresi
    today_minutes = (
        db.query(StudySession)
        .filter(
            StudySession.room_id == room_id,
            StudySession.study_date == date.today()
        )
        .with_entities(
            func.coalesce(
                func.sum(StudySession.duration_minutes),
                0
            )
        )
        .scalar()
    )

    # Aktif üyeleri say
    member_count = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.is_active == True
        )
        .count()
    )

    # Şu anda çalışan üyeleri say
    currently_studying = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.is_active == True,
            StudyRoomMember.status == "studying"
        )
        .count()
    )

    return {
        "room_id": room_id,
        "today_minutes": today_minutes,
        "total_minutes": total_minutes,
        "member_count": member_count,
        "currently_studying": currently_studying
    }

# ============================================================
# STUDY ROOM CHAT - MESAJ GÖNDER
# ============================================================

@router.post(
    "/{room_id}/messages",
    response_model=StudyRoomMessageResponse,
)
def create_study_room_message(
    room_id: int,
    message_data: StudyRoomMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True,
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya aktif değil.",
        )

    # Kullanıcının aktif üyeliğini kontrol et
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True,
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz.",
        )

    # Mesaj
    text = message_data.message.strip()

    # Materyal paylaşılmıyorsa normal mesaj olabilir.
    # Materyal varsa ID de zorunlu.
    if message_data.material_type is not None:
        if message_data.material_id is None:
            raise HTTPException(
                status_code=400,
                detail="Materyal paylaşımı için material_id gereklidir.",
            )

        material_id = message_data.material_id
        material_type = message_data.material_type

        # ----------------------------------------------------
        # DOKÜMAN KONTROLÜ
        # ----------------------------------------------------
        if material_type == "document":
            material = (
                db.query(Document)
                .join(Course, Document.course_id == Course.id)
                .filter(
                    Document.id == material_id,
                    Course.user_id == current_user.id,
                )
                .first()
            )

            if material is None:
                raise HTTPException(
                    status_code=404,
                    detail="Paylaşılmak istenen doküman bulunamadı.",
                )

        # ----------------------------------------------------
        # QUIZ KONTROLÜ
        # ----------------------------------------------------
        elif material_type == "quiz":
            material = (
                db.query(Quiz)
                .join(Document, Quiz.document_id == Document.id)
                .join(Course, Document.course_id == Course.id)
                .filter(
                    Quiz.id == material_id,
                    Course.user_id == current_user.id,
                )
                .first()
            )

            if material is None:
                raise HTTPException(
                    status_code=404,
                    detail="Paylaşılmak istenen quiz bulunamadı.",
                )

        # ----------------------------------------------------
        # FLASHCARD KONTROLÜ
        # ----------------------------------------------------
        elif material_type == "flashcard":
            material = (
                db.query(Flashcard)
                .filter(
                    Flashcard.id == material_id,
                    Flashcard.course_id.in_(
                        db.query(Course.id).filter(
                            Course.user_id == current_user.id
                        )
                    ),
                )
                .first()
            )

            if material is None:
                raise HTTPException(
                    status_code=404,
                    detail="Paylaşılmak istenen flashcard bulunamadı.",
                )

    else:
        # Normal mesajda boş metne izin verme
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Mesaj boş olamaz.",
            )

    # Materyal mesajında açıklama boş olabilir.
    # Ama hem açıklama hem materyal yoksa mesaj anlamsız olur.
    if not text and message_data.material_type is None:
        raise HTTPException(
            status_code=400,
            detail="Mesaj veya materyal bulunmalıdır.",
        )

    message = StudyRoomMessage(
        room_id=room_id,
        user_id=current_user.id,
        message=text,
        material_type=message_data.material_type,
        material_id=message_data.material_id,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return StudyRoomMessageResponse(
        id=message.id,
        room_id=message.room_id,
        user_id=message.user_id,
        username=current_user.username,
        message=message.message,
        material_type=message.material_type,
        material_id=message.material_id,
        created_at=message.created_at,
    )


# ============================================================
# STUDY ROOM CHAT - MESAJLARI GETİR
# ============================================================

@router.get(
    "/{room_id}/messages",
    response_model=list[StudyRoomMessageResponse],
)
def get_study_room_messages(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Odayı kontrol et
    study_room = (
        db.query(StudyRoom)
        .filter(
            StudyRoom.id == room_id,
            StudyRoom.is_active == True,
        )
        .first()
    )

    if study_room is None:
        raise HTTPException(
            status_code=404,
            detail="Study Room bulunamadı veya aktif değil.",
        )

    # Kullanıcının aktif üyeliğini kontrol et
    member = (
        db.query(StudyRoomMember)
        .filter(
            StudyRoomMember.room_id == room_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True,
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=403,
            detail="Bu Study Room'a üye değilsiniz.",
        )

    messages = (
        db.query(StudyRoomMessage, User)
        .join(
            User,
            StudyRoomMessage.user_id == User.id,
        )
        .filter(
            StudyRoomMessage.room_id == room_id,
        )
        .order_by(
            StudyRoomMessage.created_at.asc(),
        )
        .all()
    )

    return [
        StudyRoomMessageResponse(
            id=message.id,
            room_id=message.room_id,
            user_id=message.user_id,
            username=user.username,
            message=message.message,
            material_type=message.material_type,
            material_id=message.material_id,
            created_at=message.created_at,
        )
        for message, user in messages
    ]