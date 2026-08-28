from datetime import datetime

from pydantic import BaseModel, ConfigDict
from typing import Literal


class StudyRoomCreate(BaseModel):
    name: str
    course_id: int


class StudyRoomResponse(BaseModel):
    id: int
    name: str
    code: str
    course_id: int
    created_by: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class StudyRoomJoin(BaseModel):
    code: str

class StudyRoomMemberResponse(BaseModel):
    user_id: int
    username: str
    status: str
    joined_at: datetime
    study_started_at: datetime | None = None

class StudyRoomStatusUpdate(BaseModel):
    status: Literal["studying", "idle", "offline"]