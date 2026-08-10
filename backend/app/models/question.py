from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Question(Base):
    __tablename__ = "questions"

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

    question_type = Column(
        String,
        nullable=False
    )

    question_text = Column(
        Text,
        nullable=False
    )

    option_a = Column(String)

    option_b = Column(String)

    option_c = Column(String)

    option_d = Column(String)

    correct_answer = Column(
        String,
        nullable=False
    )

    explanation = Column(Text)

    quiz = relationship(
        "Quiz",
        back_populates="questions"
    )