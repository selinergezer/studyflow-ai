from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    APP_NAME: str = "StudyFlow AI"
    APP_VERSION: str = "1.0.0"

    DATABASE_URL: str
    SECRET_KEY: str

    GEMINI_API_KEY: str

    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()
