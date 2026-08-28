from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    room_id = Column(
    Integer,
    ForeignKey("study_rooms.id"),
    nullable=True
)

    study_date = Column(
        Date,
        nullable=False
    )

    duration_minutes = Column(
        Integer,
        nullable=False
    )

    description = Column(
        String,
        nullable=True
    )

    user = relationship(
        "User",
        back_populates="study_sessions"
    )

    course = relationship(
        "Course",
        back_populates="study_sessions"
    )

    room = relationship(
    "StudyRoom"
    )