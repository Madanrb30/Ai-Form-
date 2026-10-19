import os
import json
import logging
from typing import List, Union, Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_FALLBACK_SECRET = "voxform-dev-ephemeral-jwt-key-2026-safe-for-local-testing-only-99"

INSECURE_SECRETS = {
    "voxform-secure-production-jwt-secret-key-random-88492",
    "replace_with_a_secure_random_secret_in_production",
    "secret",
    "jwt_secret",
    "changeme",
    "your-secret-key",
    DEV_FALLBACK_SECRET,
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Voice Form Assistant"
    API_V1_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"  # "development", "testing", "production"
    DATABASE_URL: str = "sqlite:///./app.db"

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # AI Configuration (Groq is the primary provider)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_FALLBACK_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"

    # Configurable Speech-to-Text (STT) Providers (Sarvam AI primary, Groq Whisper alternative)
    STT_PROVIDER: str = "sarvam"  # "sarvam" or "groq"
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"  # "whisper-large-v3-turbo" or "whisper-large-v3"
    GROQ_STT_LANGUAGE: Optional[str] = None  # None for auto-detect; or "ta", "en"
    GROQ_STT_TEMPERATURE: float = 0.0
    GROQ_STT_PROMPT: Optional[str] = (
        "English, Tamil, Tanglish form details. Names, email, phone numbers, department names."
    )

    # Optional Sarvam AI STT Provider
    SARVAM_API_KEY: str = ""
    SARVAM_STT_MODEL: str = "saaras:v4"  # "saaras:v4" or "saaras:v3"
    SARVAM_STT_MODE: str = "codemix"  # "codemix", "transcribe", "verbatim", "translate", "translit"
    SARVAM_STT_LANGUAGE_CODE: str = "unknown"  # "unknown", "ta-IN", "en-IN"

    MAX_AUDIO_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB (Groq limit)
    DOCUMENT_PROCESSING_TIMEOUT: float = 35.0
    MAX_DOCUMENT_PAGES: int = 10
    MAX_IMAGE_DIMENSION: int = 2048
    IMAGE_BATCH_SIZE: int = 2
    AI_PROVIDER: str = "groq"
    AI_DEMO_MODE: bool = False
    ALLOW_PRODUCTION_DEMO_MODE: bool = False

    # Legacy AI migration support (optional)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Security & Authentication
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SEED_DEMO_USER: bool = False  # Disabled by default; prohibited in production
    GOOGLE_CLIENT_ID: Optional[str] = ""

    # One-Time Super Admin Bootstrap
    BOOTSTRAP_SECRET_KEY: str = ""
    BOOTSTRAP_SUPER_ADMIN_EMAIL: str = ""
    BOOTSTRAP_SUPER_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_SUPER_ADMIN_NAME: str = "Super Administrator"

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

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            clean_str = v.strip()
            if clean_str.startswith("[") and clean_str.endswith("]"):
                try:
                    return json.loads(clean_str)
                except Exception:
                    pass
            return [origin.strip() for origin in clean_str.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_and_secrets(self):
        is_production = self.ENVIRONMENT.lower() == "production"

        # 1. Enforce JWT Secret
        secret = (self.JWT_SECRET_KEY or "").strip()
        if is_production:
            if not secret or len(secret) < 32 or secret in INSECURE_SECRETS:
                raise ValueError(
                    "Production configuration error: A strong, unique JWT_SECRET_KEY "
                    "(at least 32 characters) must be configured in production environment."
                )
            if self.SEED_DEMO_USER:
                raise ValueError(
                    "Production configuration error: SEED_DEMO_USER is prohibited in production."
                )
        else:
            if not secret or secret in INSECURE_SECRETS:
                # Use development fallback secret for local dev/test if not specified in .env
                self.JWT_SECRET_KEY = DEV_FALLBACK_SECRET

        # 2. Production AI Demo Mode check
        if is_production and self.AI_DEMO_MODE and not self.ALLOW_PRODUCTION_DEMO_MODE:
            raise ValueError(
                "Production configuration error: AI_DEMO_MODE cannot be enabled in production "
                "without explicit ALLOW_PRODUCTION_DEMO_MODE=True."
            )

        # 3. Production Live AI key check
        if is_production and not self.AI_DEMO_MODE and not self.GROQ_API_KEY.strip():
            raise ValueError(
                "Production configuration error: GROQ_API_KEY must be provided when live AI is active in production."
            )

        # 4. CORS wildcards check in production
        if is_production and ("*" in self.CORS_ORIGINS):
            raise ValueError(
                "Production configuration error: Wildcard '*' is not permitted in CORS_ORIGINS when credentials are enabled."
            )

        # 5. Production Bootstrap Secret Key check
        bootstrap_key = (self.BOOTSTRAP_SECRET_KEY or "").strip()
        if is_production and bootstrap_key:
            if len(bootstrap_key) < 32 or bootstrap_key in INSECURE_SECRETS:
                raise ValueError(
                    "Production configuration error: When BOOTSTRAP_SECRET_KEY is configured in production, "
                    "it must be at least 32 characters and cryptographically secure."
                )

        # 6. STT Provider validation
        provider = (self.STT_PROVIDER or "groq").strip().lower()
        if provider not in ("groq", "sarvam"):
            raise ValueError(
                f"Configuration error: Unsupported STT_PROVIDER '{self.STT_PROVIDER}'. Supported options: 'groq', 'sarvam'."
            )

        if provider == "sarvam" and not self.AI_DEMO_MODE:
            if is_production and not (self.SARVAM_API_KEY or "").strip():
                raise ValueError(
                    "Production configuration error: SARVAM_API_KEY must be provided when STT_PROVIDER='sarvam'."
                )

        # Synchronize backward-compatible GROQ_TRANSCRIPTION_MODEL and GROQ_STT_MODEL
        if self.GROQ_STT_MODEL and self.GROQ_STT_MODEL != "whisper-large-v3-turbo":
            self.GROQ_TRANSCRIPTION_MODEL = self.GROQ_STT_MODEL
        elif self.GROQ_TRANSCRIPTION_MODEL and self.GROQ_TRANSCRIPTION_MODEL != "whisper-large-v3-turbo":
            self.GROQ_STT_MODEL = self.GROQ_TRANSCRIPTION_MODEL

        return self


settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
