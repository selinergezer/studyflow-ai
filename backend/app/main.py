from fastapi import FastAPI

from app.db.database import Base, engine

# Modelleri import etmezsek SQLAlchemy tabloyu oluşturamaz.
from app.models.user import User
from app.api.user import router as user_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="StudyFlow AI API",
    version="1.0.0"
)

app.include_router(user_router)

@app.get("/")
def root():
    return {
        "message": "Welcome to StudyFlow AI API 🚀"
    }