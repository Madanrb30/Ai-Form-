import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.services.stt.base import BaseSTTProvider
from app.services.ai_provider import AIProviderError

logger = logging.getLogger("ai_voice_form.stt.sarvam")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


class SarvamSTTProvider(BaseSTTProvider):
    """
    Speech-to-Text provider powered by Sarvam AI's Saaras models:
    - saaras:v4 (latest, 23 Indic languages + English, specialized for code-mixed Tanglish)
    - saaras:v3 (previous generation)
    """

    def __init__(self, api_key: Optional[str] = None, http_client: Optional[httpx.Client] = None, model: Optional[str] = None):
        self._api_key = api_key
        self._http_client = http_client
        self._model = model

    @property
    def name(self) -> str:
        return "sarvam"

    @property
    def model(self) -> str:
        return self._model or getattr(settings, "SARVAM_STT_MODEL", "saaras:v4") or "saaras:v4"

    def _get_api_key(self) -> str:
        key = self._api_key or getattr(settings, "SARVAM_API_KEY", "") or ""
        if not key.strip():
            raise AIProviderError(
                "SARVAM_API_KEY is not configured on the backend. Please set SARVAM_API_KEY in backend/.env when STT_PROVIDER='sarvam'.",
                status_code=503,
                is_retryable=False,
            )
        return key.strip()

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

        api_key = self._get_api_key()
        model_name = self.model
        mode = getattr(settings, "SARVAM_STT_MODE", "codemix") or "codemix"
        lang_code = (language or "").strip() or getattr(settings, "SARVAM_STT_LANGUAGE_CODE", "unknown") or "unknown"

        headers = {
            "api-subscription-key": api_key,
        }

        # Sarvam multipart form parameters
        files = {
            "file": (filename, audio_bytes, content_type),
        }
        data: Dict[str, str] = {
            "model": model_name,
            "mode": mode,
        }
        if lang_code and lang_code.lower() != "unknown":
            data["language_code"] = lang_code

        try:
            if self._http_client:
                response = self._http_client.post(
                    SARVAM_STT_URL,
                    headers=headers,
                    files=files,
                    data=data,
                )
            else:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        SARVAM_STT_URL,
                        headers=headers,
                        files=files,
                        data=data,
                    )

            if response.status_code == 401:
                logger.error(f"Sarvam AI authentication failed: {response.text}")
                raise AIProviderError("Invalid SARVAM_API_KEY configured on server.", status_code=401)
            elif response.status_code == 429:
                logger.error(f"Sarvam AI rate limit reached: {response.text}")
                raise AIProviderError(
                    "Sarvam AI rate limit exceeded. Please try again shortly.",
                    status_code=429,
                    is_retryable=True,
                )
            elif response.status_code == 400:
                logger.error(f"Sarvam AI bad request: {response.text}")
                raise AIProviderError(
                    f"Sarvam AI transcription rejected audio: {response.text}",
                    status_code=400,
                )
            elif response.status_code >= 500:
                logger.error(f"Sarvam AI service error ({response.status_code}): {response.text}")
                raise AIProviderError(
                    f"Sarvam AI service error ({response.status_code}).",
                    status_code=502,
                )
            elif response.status_code != 200:
                logger.error(f"Sarvam AI unexpected status ({response.status_code}): {response.text}")
                raise AIProviderError(
                    f"Sarvam AI transcription error: {response.text}",
                    status_code=response.status_code,
                )

            res_json = response.json()
            transcript = res_json.get("transcript", "") or ""
            detected_lang = res_json.get("language_code", lang_code or "ta-IN")

            return {
                "text": transcript.strip(),
                "model": model_name,
                "duration": None,
                "language": detected_lang,
                "provider": "sarvam",
            }
        except httpx.TimeoutException as e:
            logger.error(f"Sarvam AI connection timeout: {e}")
            raise AIProviderError(
                "Could not connect to Sarvam AI Speech-to-Text service. Network timeout.",
                status_code=504,
                is_retryable=True,
            )
        except httpx.RequestError as e:
            logger.error(f"Sarvam AI request error: {e}")
            raise AIProviderError(
                f"Sarvam AI connection failed: {str(e)}",
                status_code=504,
                is_retryable=True,
            )
        except AIProviderError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Sarvam transcription: {e}")
            raise AIProviderError(f"Sarvam transcription failed: {str(e)}", status_code=500)
