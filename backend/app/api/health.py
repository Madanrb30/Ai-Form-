from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.core.config import settings
from app.services.ai_provider import ai_provider

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        from app.core.logging import logger
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"


    is_ai_active = ai_provider.is_groq_configured()
    ai_mode = "groq" if is_ai_active else "demo"

    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "database": db_status,
        "ai_mode": ai_mode,
        "ai_provider": settings.AI_PROVIDER,
        "model": settings.GROQ_MODEL if is_ai_active else "offline_demo_generator",
        "vision_model": settings.GROQ_VISION_MODEL if is_ai_active else "offline_demo",
        "transcription_model": settings.GROQ_TRANSCRIPTION_MODEL if is_ai_active else "offline_demo",
    }
