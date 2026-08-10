from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String,
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    course = relationship(
        "Course",
        back_populates="quizzes"
    )

    document = relationship(
        "Document",
        back_populates="quizzes"
    )

    questions = relationship(
        "Question",
        back_populates="quiz",
        cascade="all, delete"
    )

    attempts = relationship(
    "QuizAttempt",
    back_populates="quiz",
    cascade="all, delete"
    )