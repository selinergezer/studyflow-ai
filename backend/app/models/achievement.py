from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Achievement(Base):
    __tablename__ = "achievements"

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

    achievement_type = Column(
        String,
        nullable=False
    )

    title = Column(
        String,
        nullable=False
    )

    description = Column(
        String,
        nullable=False
    )

    completed = Column(
        Boolean,
        default=False
    )

    user = relationship(
        "User",
        back_populates="achievements"
    )