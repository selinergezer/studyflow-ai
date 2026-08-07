from fastapi import FastAPI

from app.db.database import Base, engine

# Modelleri import etmezsek SQLAlchemy tabloyu oluşturamaz.
from app.models.user import User
from app.api.user import router as user_router

from app.api.course import router as course_router

from app.models.course import Course

from app.models.document import Document

from app.api.document import router as document_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="StudyFlow AI API",
    version="1.0.0"
)

app.include_router(user_router)
app.include_router(course_router)
app.include_router(document_router)

@app.get("/")
def root():
    return {
        "message": "Welcome to StudyFlow AI API 🚀"
    }