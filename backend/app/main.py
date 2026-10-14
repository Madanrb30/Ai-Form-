from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import logger
from app.db.init_db import init_db
from app.api.health import router as health_router
from app.api.forms import router as forms_router
from app.api.auth import router as auth_router
from app.api.voice import router as voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    init_db()
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for AI Voice-Assisted Dynamic Form Builder",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(health_router, prefix="/api")
app.include_router(forms_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(voice_router, prefix="/api")

from fastapi.responses import JSONResponse
from app.services.ai_provider import AIProviderError

@app.exception_handler(AIProviderError)
async def ai_provider_exception_handler(request, exc: AIProviderError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "is_retryable": exc.is_retryable}
    )


@app.get("/")
def root():
    return {
        "message": "AI Voice-Assisted Dynamic Form Builder API is running.",
        "health": "/api/health",
        "docs": "/docs",
    }
