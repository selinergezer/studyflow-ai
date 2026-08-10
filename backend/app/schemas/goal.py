from pydantic import BaseModel
from datetime import date


class GoalCreate(BaseModel):
    title: str
    goal_type: str
    target_value: float
    start_date: date
    end_date: date
    course_id: int | None = None


class GoalUpdate(BaseModel):
    title: str | None = None
    goal_type: str | None = None
    target_value: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    course_id: int | None = None


class GoalResponse(BaseModel):
    id: int
    title: str
    goal_type: str
    target_value: float
    current_value: float
    start_date: date
    end_date: date
    completed: bool
    course_id: int | None = None

    class Config:
        from_attributes = True