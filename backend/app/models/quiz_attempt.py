from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    quiz_id = Column(
        Integer,
        ForeignKey("quizzes.id"),
        nullable=False
    )

    score = Column(
        Integer,
        nullable=False
    )

    correct_count = Column(
        Integer,
        nullable=False
    )

    wrong_count = Column(
        Integer,
        nullable=False
    )

    total_questions = Column(
        Integer,
        nullable=False
    )

    completed_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    quiz = relationship(
        "Quiz",
        back_populates="attempts"
    )