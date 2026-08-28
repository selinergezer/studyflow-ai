from pydantic import BaseModel
from datetime import date
from typing import Optional


class StudySessionCreate(BaseModel):
    course_id: int
    study_date: date
    duration_minutes: int
    description: Optional[str] = None


class StudySessionUpdate(BaseModel):
    course_id: Optional[int] = None
    study_date: Optional[date] = None
    duration_minutes: Optional[int] = None
    description: Optional[str] = None


class StudySessionResponse(BaseModel):
    id: int
    course_id: int
    study_date: date
    duration_minutes: int
    description: Optional[str] = None

    class Config:
        from_attributes = True