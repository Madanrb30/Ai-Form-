import os
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends

from app.core.config import settings
from app.core.logging import logger
from app.services.ai_provider import ai_provider, AIProviderError
from app.schemas.voice import TranscriptionResponse
from app.models.user import User
from app.api.deps import get_current_user_optional

router = APIRouter(prefix="/voice", tags=["Voice & Speech-to-Text"])

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm", ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".mp4", ".mpeg", ".mpga"
}

ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/webm", "video/webm",
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/mpeg", "audio/mp3",
    "audio/m4a", "audio/x-m4a",
    "audio/mp4", "video/mp4",
    "audio/ogg", "application/ogg",
    "audio/flac", "audio/x-flac",
    "application/octet-stream"  # Browser blobs sometimes omit exact subtype
}


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    prompt: Optional[str] = Form(default=None),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Cloud-based speech-to-text audio transcription using Groq's hosted whisper-large-v3-turbo API.
    Zero local AI inference (lightweight, runs completely on Groq cloud infrastructure).
    """
    filename = file.filename or "recording.webm"
    ext = os.path.splitext(filename)[1].lower()

    # Fallback extension if generic blob name
    if not ext:
        if file.content_type and "wav" in file.content_type:
            ext = ".wav"
        elif file.content_type and "mp4" in file.content_type:
            ext = ".mp4"
        else:
            ext = ".webm"
        filename = f"recording{ext}"

    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format '{ext}'. Supported formats: WebM, WAV, MP3, M4A, OGG, FLAC, MP4."
        )

    audio_bytes = await file.read()

    # 1. Reject empty recordings (0 bytes)
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording is empty (0 bytes). Please record again."
        )

    # 2. Reject oversized audio
    if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
        max_mb = settings.MAX_AUDIO_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds maximum size limit of {max_mb} MB."
        )

    # 3. Transcribe via Groq Whisper API
    try:
        content_type = file.content_type or "audio/webm"
        result = ai_provider.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language=language,
            prompt=prompt,
        )
        return TranscriptionResponse(**result)
    except AIProviderError as e:
        logger.error(f"Transcription error: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error in transcribe_speech: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Speech transcription failed due to an unexpected internal error. Please try again."
        )

