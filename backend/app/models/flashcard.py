from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    question = Column(
        Text,
        nullable=False
    )

    answer = Column(
        Text,
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

    review_count = Column(
        Integer,
        default=0
    )

    correct_count = Column(
        Integer,
        default=0
    )

    wrong_count = Column(
        Integer,
        default=0
    )

    next_review = Column(
        DateTime(timezone=True),
        nullable=True
    )

    course = relationship(
        "Course",
        back_populates="flashcards"
    )

    document = relationship(
        "Document",
        back_populates="flashcards"
    )