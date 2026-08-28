from pydantic import BaseModel
from datetime import date
from typing import Optional


class GoalCreate(BaseModel):
    title: str
    goal_type: str
    target_value: float
    start_date: date
    end_date: date
    course_id: Optional[int] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    goal_type: Optional[str] = None
    target_value: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    course_id: Optional[int] = None


class GoalResponse(BaseModel):
    id: int
    title: str
    goal_type: str
    target_value: float
    current_value: float
    start_date: date
    end_date: date
    completed: bool
    course_id: Optional[int] = None

    class Config:
        from_attributes = True