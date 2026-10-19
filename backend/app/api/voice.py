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
    provider: Optional[str] = Form(default=None),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Cloud-based speech-to-text audio transcription using configured provider (Groq Whisper or Sarvam AI).
    Zero local AI inference (lightweight, runs completely on cloud infrastructure).
    """
    filename = file.filename or "recording.webm"
    ext = os.path.splitext(filename)[1].lower()

    raw_content_type = file.content_type or ""
    clean_mime = raw_content_type.split(";")[0].strip().lower()

    # Fallback extension if generic blob name
    if not ext:
        if clean_mime in ("audio/wav", "audio/x-wav", "audio/wave"):
            ext = ".wav"
        elif clean_mime in ("audio/mp4", "audio/x-m4a", "video/mp4"):
            ext = ".mp4"
        elif clean_mime in ("audio/ogg", "application/ogg"):
            ext = ".ogg"
        elif clean_mime in ("audio/mpeg", "audio/mp3"):
            ext = ".mp3"
        elif clean_mime in ("audio/flac", "audio/x-flac"):
            ext = ".flac"
        else:
            ext = ".webm"
        filename = f"recording{ext}"

    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format '{ext}'. Supported formats: WebM, WAV, MP3, M4A, OGG, FLAC, MP4."
        )

    audio_bytes = await file.read()

    # Import container inspector for safe diagnostic logging and validation
    from app.services.stt.sarvam_provider import detect_audio_container
    detected_container = detect_audio_container(audio_bytes)

    # Safe diagnostic logging (metadata only; NO audio contents, tokens, or user data)
    logger.info(
        f"Audio upload received: byte_length={len(audio_bytes)}, "
        f"normalized_mime='{clean_mime}', detected_container='{detected_container}', "
        f"filename_ext='{ext}'"
    )

    # 1. Reject empty recordings
    if not audio_bytes or len(audio_bytes) == 0:
        logger.warning("Rejected empty audio payload (0 bytes).")
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

    # 3. Reject undersized audio in non-testing environments (< 200 bytes contains no decodable speech frames)
    if getattr(settings, "ENVIRONMENT", "") != "testing" and len(audio_bytes) < 200:
        logger.warning(f"Rejected undersized audio payload: {len(audio_bytes)} bytes.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording contains no decodable speech (under 200 bytes). Please record again."
        )

    # 3. Align filename extension with genuine detected container format
    if detected_container:
        expected_ext = f".{detected_container}"
        if detected_container == "mp3":
            expected_ext = ".mp3"
        if ext != expected_ext:
            filename = f"{os.path.splitext(filename)[0]}{expected_ext}"
            ext = expected_ext

    # 4. Transcribe via configured STT provider (Sarvam AI or Groq Whisper)
    try:
        content_type = clean_mime or "audio/webm"
        result = ai_provider.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language=language,
            prompt=prompt,
            provider_name=provider,
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

