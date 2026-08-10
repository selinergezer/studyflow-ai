from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    description = Column(String)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    owner = relationship(
        "User",
        back_populates="courses"
    )

    documents = relationship(
        "Document",
        back_populates="course",
        cascade="all, delete"
    )

    quizzes = relationship(
        "Quiz",
        back_populates="course",
        cascade="all, delete"
    )

    flashcards = relationship(
    "Flashcard",
    back_populates="course",
    cascade="all, delete"
   )