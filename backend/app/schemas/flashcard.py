from pydantic import BaseModel


class FlashcardReview(BaseModel):
    result: str