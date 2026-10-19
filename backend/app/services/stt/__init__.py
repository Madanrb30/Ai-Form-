import logging
from typing import Optional, Dict, Any

from app.core.config import settings
from app.services.stt.base import BaseSTTProvider
from app.services.stt.groq_provider import GroqSTTProvider
from app.services.stt.sarvam_provider import SarvamSTTProvider
from app.services.ai_provider import AIProviderError

logger = logging.getLogger("ai_voice_form.stt")


def get_stt_provider(provider_name: Optional[str] = None) -> BaseSTTProvider:
    """
    Factory function to instantiate the configured Speech-to-Text provider.
    Supported providers:
    - "sarvam" (primary default): Sarvam AI Saaras (saaras:v4, saaras:v3)
    - "groq" (alternative): Groq Whisper (whisper-large-v3-turbo, whisper-large-v3)
    """
    name = (provider_name or getattr(settings, "STT_PROVIDER", "sarvam") or "sarvam").lower().strip()
    if name == "sarvam":
        return SarvamSTTProvider()
    elif name == "groq":
        return GroqSTTProvider()
    else:
        raise AIProviderError(
            f"Unsupported STT_PROVIDER '{name}'. Supported providers: 'sarvam', 'groq'.",
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

    Behavior & Fallback Policy:
    1. Primary provider is Sarvam AI (or whatever STT_PROVIDER specifies).
    2. Groq Whisper remains available as an alternative selectable provider.
    3. Automatic fallback is ONLY triggered for genuine provider infrastructure failures
       (HTTP 502/503/504, 429 rate limit, network timeouts, or missing server API key)
       when the user is using the default provider.
    4. Automatic fallback is NEVER triggered for client errors (400, empty audio) or
       merely because a transcript is empty or inaccurate.
    5. If caller explicitly passed a provider name (e.g. provider='sarvam' or 'groq'),
       their choice is strictly respected without fallback.
    """
    primary_name = (provider_name or getattr(settings, "STT_PROVIDER", "sarvam") or "sarvam").lower().strip()
    provider = get_stt_provider(primary_name)

    try:
        return provider.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language=language,
            prompt=prompt,
        )
    except AIProviderError as e:
        # Check if fallback is appropriate:
        # 1. Primary provider rejected audio due to 30-second duration limit (fallback to Groq Whisper which handles long recordings)
        err_msg_lower = (e.message or "").lower()
        is_duration_limit_failure = (
            e.status_code == 400
            and primary_name == "sarvam"
            and any(phrase in err_msg_lower for phrase in [
                "duration exceeds", "30 seconds", "limit of 30", "batch api", "longer audio"
            ])
        )

        # 2. Primary provider suffered a format-read failure on genuine audio (e.g. Sarvam "Failed to read the file")
        is_format_read_failure = (
            e.status_code == 400
            and primary_name == "sarvam"
            and "failed to read the file" in err_msg_lower
            and len(audio_bytes) >= 500
        )

        # 3. Provider infrastructure error (502, 503, 504, 429, timeout, connection failure)
        is_infra_failure = e.status_code in (429, 502, 503, 504) or getattr(e, "is_retryable", False)

        # Long audio exceeding Sarvam 30s limit triggers automatic fallback to Groq Whisper seamlessly.
        # General infra/format failures trigger fallback when user is on the default provider.
        should_fallback = is_duration_limit_failure or ((provider_name is None) and (is_infra_failure or is_format_read_failure))

        if not should_fallback:
            raise

        alt_provider_name = "groq" if primary_name == "sarvam" else "sarvam"
        if is_duration_limit_failure:
            logger.warning(
                f"Primary STT provider '{primary_name}' rejected audio due to 30-second duration limit. "
                f"Seamlessly falling back to '{alt_provider_name}' (Whisper) for long recording transcription."
            )
        else:
            logger.warning(
                f"Primary STT provider '{primary_name}' failed with {e.status_code} ({e.message}). "
                f"Triggering automated fallback to '{alt_provider_name}'."
            )

        try:
            alt_provider = get_stt_provider(alt_provider_name)
            res = alt_provider.transcribe(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=content_type,
                language=language,
                prompt=prompt,
            )
            res["fallback_used"] = True
            res["primary_provider_error"] = e.message
            if is_duration_limit_failure:
                res["fallback_reason"] = "Audio duration exceeded Sarvam 30s limit; transcribed with Groq Whisper fallback."
            return res
        except Exception as alt_err:
            logger.error(f"Alternative STT provider '{alt_provider_name}' also failed: {alt_err}")
            # Re-raise the primary provider error for transparency
            raise e
