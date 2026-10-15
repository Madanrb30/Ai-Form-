from typing import Optional, Dict, Any

from app.core.config import settings
from app.services.stt.base import BaseSTTProvider
from app.services.stt.groq_provider import GroqSTTProvider
from app.services.stt.sarvam_provider import SarvamSTTProvider
from app.services.ai_provider import AIProviderError


def get_stt_provider(provider_name: Optional[str] = None) -> BaseSTTProvider:
    """
    Factory function to instantiate the configured Speech-to-Text provider.
    Supported providers:
    - "groq" (default): Groq Whisper (whisper-large-v3-turbo, whisper-large-v3)
    - "sarvam": Sarvam AI Saaras (saaras:v4, saaras:v3)
    """
    name = (provider_name or getattr(settings, "STT_PROVIDER", "groq") or "groq").lower().strip()
    if name == "groq":
        return GroqSTTProvider()
    elif name == "sarvam":
        return SarvamSTTProvider()
    else:
        raise AIProviderError(
            f"Unsupported STT_PROVIDER '{name}'. Supported providers: 'groq', 'sarvam'.",
            status_code=400,
            is_retryable=False,
        )


def transcribe_speech_audio(
    audio_bytes: bytes,
    filename: str = "recording.webm",
    content_type: str = "audio/webm",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    High-level entry point to transcribe audio bytes with the active or requested provider.
    """
    provider = get_stt_provider(provider_name)
    return provider.transcribe(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=content_type,
        language=language,
        prompt=prompt,
    )
