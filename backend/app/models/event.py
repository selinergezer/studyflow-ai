from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Event(Base):
    __tablename__ = "events"

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
        nullable=True
    )

    title = Column(
        String,
        nullable=False
    )

    description = Column(
        String,
        nullable=True
    )

    event_type = Column(
        String,
        nullable=False
    )

    start_date = Column(
        DateTime(timezone=True),
        nullable=False
    )

    end_date = Column(
        DateTime(timezone=True),
        nullable=True
    )

    completed = Column(
        Boolean,
        default=False
    )

    user = relationship(
        "User",
        back_populates="events"
    )

    course = relationship(
        "Course",
        back_populates="events"
    )