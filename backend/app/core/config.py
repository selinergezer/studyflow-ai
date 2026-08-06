from dotenv import load_dotenv
import os

# .env dosyasını yükle
load_dotenv()


class Settings:
    APP_NAME = "StudyFlow AI"
    APP_VERSION = "1.0.0"

    DATABASE_URL = os.getenv("DATABASE_URL")
    SECRET_KEY = os.getenv("SECRET_KEY")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")


settings = Settings()