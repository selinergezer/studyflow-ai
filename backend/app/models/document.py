from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base

from sqlalchemy import Text

from app.services.ai_service import generate_summary


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)

    file_path = Column(String, nullable=False)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    course_id = Column(Integer, ForeignKey("courses.id"))

    course = relationship("Course", back_populates="documents")

    text = Column(Text)

    summary = Column(Text)

    page_count = Column(Integer)