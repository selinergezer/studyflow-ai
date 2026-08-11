from fastapi import FastAPI

from app.db.database import Base, engine

from fastapi.middleware.cors import CORSMiddleware


# =========================
# MODELLER
# =========================

from app.models.user import User
from app.models.course import Course
from app.models.document import Document
from app.models.quiz import Quiz
from app.models.question import Question
from app.models.flashcard import Flashcard
from app.models.quiz_attempt import QuizAttempt
from app.models.goal import Goal
from app.models.achievement import Achievement
from app.models.event import Event

# =========================
# API ROUTERLARI
# =========================

from app.api.user import router as user_router
from app.api.course import router as course_router
from app.api.document import router as document_router
from app.api.quiz import router as quiz_router
from app.api.flashcard import router as flashcard_router
from app.api.stats import router as stats_router
from app.api.goal import router as goal_router
from app.api.achievement import router as achievement_router
from app.api.event import router as event_router
from app.api.dashboard import router as dashboard_router
from app.api.chat import router as chat_router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# ROUTERLAR
# =========================

app.include_router(user_router)
app.include_router(course_router)
app.include_router(document_router)
app.include_router(quiz_router)
app.include_router(flashcard_router)
app.include_router(stats_router)
app.include_router(goal_router)
app.include_router(achievement_router)
app.include_router(event_router)
app.include_router(dashboard_router)
app.include_router(chat_router)

@app.get("/")
def root():
    return {
        "message": "Welcome to StudyFlow AI API 🚀"
    }