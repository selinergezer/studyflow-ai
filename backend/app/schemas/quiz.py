from pydantic import BaseModel


class QuizAnswer(BaseModel):
    question_id: int
    answer: str


class QuizSubmit(BaseModel):
    answers: list[QuizAnswer]