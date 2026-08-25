from pydantic import BaseModel
from typing import Optional


class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CourseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True