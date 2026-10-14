import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Voice Form Assistant"
    API_V1_PREFIX: str = "/api"
    DATABASE_URL: str = "sqlite:///./app.db"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    MAX_AUDIO_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB (Groq limit)
    DOCUMENT_PROCESSING_TIMEOUT: float = 35.0
    MAX_DOCUMENT_PAGES: int = 10
    MAX_IMAGE_DIMENSION: int = 2048
    IMAGE_BATCH_SIZE: int = 2
    AI_PROVIDER: str = "groq"
    AI_DEMO_MODE: bool = True

    # Gemini settings (Legacy/Fallback migration support)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Security & Authentication
    JWT_SECRET_KEY: str = "voxform-secure-production-jwt-secret-key-random-88492"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # File Uploads
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB

    # Server configuration
    HOST: str = "127.0.0.1"
    PORT: int = 8090
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
