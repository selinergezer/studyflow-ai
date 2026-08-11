from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    username = Column(
        String,
        unique=True,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        nullable=False
    )

    password = Column(
        String,
        nullable=False
    )

    courses = relationship(
        "Course",
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    achievements = relationship(
        "Achievement",
        back_populates="user",
        cascade="all, delete-orphan"
   )

    goals = relationship(
        "Goal",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    events = relationship(
        "Event",
        back_populates="user"
    )
