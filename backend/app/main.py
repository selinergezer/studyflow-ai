from fastapi import FastAPI

from app.db.database import Base, engine

# =========================
# MODELLER
# =========================

from app.models.user import User
from app.models.course import Course
from app.models.document import Document
from app.models.quiz import Quiz
from app.models.question import Question

# =========================
# API ROUTERLARI
# =========================

from app.api.user import router as user_router
from app.api.course import router as course_router
from app.api.document import router as document_router
from app.api.quiz import router as quiz_router

from app.models.quiz_attempt import QuizAttempt

# =========================
# DATABASE
# =========================

Base.metadata.create_all(bind=engine)

# =========================
# FASTAPI
# =========================

app = FastAPI(
    title="StudyFlow AI API",
    version="1.0.0"
)

# =========================
# ROUTERLAR
# =========================

app.include_router(user_router)
app.include_router(course_router)
app.include_router(document_router)
app.include_router(quiz_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to StudyFlow AI API 🚀"
    }