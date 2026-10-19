import logging
from typing import Dict, Any, Optional
from groq import Groq, AuthenticationError, RateLimitError, APIError, APIConnectionError, APITimeoutError

from app.core.config import settings
from app.services.stt.base import BaseSTTProvider
from app.services.ai_provider import AIProviderError

logger = logging.getLogger("ai_voice_form.stt.groq")


class GroqSTTProvider(BaseSTTProvider):
    """
    Speech-to-Text provider powered by Groq's cloud-hosted Whisper models:
    - whisper-large-v3-turbo (default, fast, 216x real-time)
    - whisper-large-v3 (flagship multilingual accuracy)
    """

    def __init__(self, client: Optional[Groq] = None, model: Optional[str] = None):
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "groq"

    @property
    def model(self) -> str:
        return self._model or getattr(settings, "GROQ_STT_MODEL", None) or settings.GROQ_TRANSCRIPTION_MODEL

    def _get_client(self) -> Groq:
        if self._client:
            return self._client
        from app.services.ai_provider import ai_provider
        return ai_provider._get_client()

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "recording.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not audio_bytes or len(audio_bytes) == 0:
            raise AIProviderError("Audio recording is empty (0 bytes).", status_code=400)

        if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
            max_mb = settings.MAX_AUDIO_SIZE_BYTES // (1024 * 1024)
            raise AIProviderError(
                f"Audio file exceeds maximum size limit of {max_mb} MB.", status_code=413
            )

        client = self._get_client()
        model_name = self.model

        # Language selection:
        # If caller passed an explicit language, respect it.
        # Otherwise fall back to GROQ_STT_LANGUAGE. If empty/None, Whisper auto-detects language.
        effective_language = (language or "").strip() or (getattr(settings, "GROQ_STT_LANGUAGE", None) or "").strip() or None

        # Prompt conditioning (critical for Tanglish / Tamil-English mixed vocabulary):
        effective_prompt = (prompt or "").strip() or (getattr(settings, "GROQ_STT_PROMPT", None) or "").strip() or None

        temperature = getattr(settings, "GROQ_STT_TEMPERATURE", 0.0)

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "file": (filename, audio_bytes, content_type),
            "response_format": "verbose_json",
            "temperature": temperature,
        }
        if effective_language:
            # Whisper requires ISO 639-1 codes (e.g. 'en', 'ta', 'hi') instead of BCP-47 regional tags ('en-IN', 'ta-IN')
            clean_lang = effective_language.split("-")[0].split("_")[0].lower().strip()
            if clean_lang:
                kwargs["language"] = clean_lang
        if effective_prompt:
            kwargs["prompt"] = effective_prompt

        try:
            transcription = client.audio.transcriptions.create(**kwargs)

            text = getattr(transcription, "text", "") or ""
            duration = getattr(transcription, "duration", None)
            detected_lang = getattr(transcription, "language", None)

            return {
                "text": text.strip(),
                "model": model_name,
                "duration": duration,
                "language": detected_lang or effective_language or "en",
                "provider": "groq",
            }
        except AuthenticationError as e:
            logger.error(f"Groq authentication error in transcription: {e}")
            raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
        except RateLimitError as e:
            logger.error(f"Groq rate limit exceeded in transcription: {e}")
            raise AIProviderError(
                "Groq Whisper API rate limit exceeded. Please try again shortly.",
                status_code=429,
                is_retryable=True,
            )
        except (APIConnectionError, APITimeoutError) as e:
            logger.error(f"Groq connection error in transcription: {e}")
            raise AIProviderError(
                "Could not connect to Groq Speech-to-Text service. Network timeout.",
                status_code=504,
                is_retryable=True,
            )
        except APIError as e:
            logger.error(f"Groq API error in transcription: {e}")
            raise AIProviderError(f"Groq Whisper service error: {e.message}", status_code=502)
        except AIProviderError:
            raise
        except Exception as e:
            logger.error(f"Audio transcription failed: {e}")
            raise AIProviderError(f"Speech transcription failed: {str(e)}", status_code=500)
