from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class StudyRoomMember(Base):
    __tablename__ = "study_room_members"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    room_id = Column(
        Integer,
        ForeignKey("study_rooms.id"),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    joined_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    study_started_at = Column(
    DateTime,
    nullable=True
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    status = Column(
        String,
        default="idle",
        nullable=False
    )

    room = relationship(
        "StudyRoom"
    )

    user = relationship(
        "User"
    )