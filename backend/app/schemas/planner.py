
from pydantic import BaseModel, Field
from typing import List

class PlannerRequest(BaseModel):
    available_hours_per_day: float = Field(gt=0, le=24)


class StudyPlanItem(BaseModel):
    day: str
    course: str
    duration_minutes: int
    topics: List[str] = Field(default_factory=list)
    reason: str


class PlannerResponse(BaseModel):
    weekly_plan: List[StudyPlanItem]
    general_advice: str
