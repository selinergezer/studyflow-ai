from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class StudyRoomMessage(Base):
    __tablename__ = "study_room_messages"

    id = Column(Integer, primary_key=True, index=True)

    room_id = Column(
        Integer,
        ForeignKey("study_rooms.id"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    message = Column(
        Text,
        nullable=False,
    )

    # Paylaşılan materyalin türü.
    # null = normal chat mesajı
    # document = PDF/doküman
    # quiz = quiz
    # flashcard = flashcard
    material_type = Column(
        String(20),
        nullable=True,
    )

    # Paylaşılan materyalin kendi tablosundaki ID'si.
    material_id = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    room = relationship(
        "StudyRoom",
        backref="messages",
    )

    user = relationship(
        "User",
        backref="study_room_messages",
    )