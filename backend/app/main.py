from fastapi import FastAPI

app = FastAPI(
    title="StudyFlow AI API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Welcome to StudyFlow AI API 🚀"
    }