from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


MaterialType = Literal[
    "document",
    "quiz",
    "flashcard",
]


class StudyRoomMessageCreate(BaseModel):
    message: str

    material_type: MaterialType | None = None
    material_id: int | None = None


class StudyRoomMessageResponse(BaseModel):
    id: int
    room_id: int
    user_id: int
    username: str
    message: str

    material_type: MaterialType | None = None
    material_id: int | None = None

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)