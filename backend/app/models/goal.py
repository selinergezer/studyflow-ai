from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Goal(Base):
    __tablename__ = "goals"

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

    goal_type = Column(
        String,
        nullable=False
    )

    target_value = Column(
        Float,
        nullable=False
    )

    current_value = Column(
        Float,
        default=0
    )

    start_date = Column(
        Date,
        nullable=False
    )

    end_date = Column(
        Date,
        nullable=False
    )

    completed = Column(
        Boolean,
        default=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    user = relationship(
        "User",
        back_populates="goals"
    )

    course = relationship(
        "Course",
        back_populates="goals"
    )