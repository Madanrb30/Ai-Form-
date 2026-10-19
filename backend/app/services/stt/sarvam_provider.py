import os
import json
import re
import logging
from typing import Dict, Any, Optional, Tuple
import httpx

from app.core.config import settings
from app.services.stt.base import BaseSTTProvider
from app.services.ai_provider import AIProviderError

logger = logging.getLogger("ai_voice_form.stt.sarvam")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


def normalize_mime_type(content_type: Optional[str]) -> str:
    """
    Strips parameters (e.g. ';codecs=opus', '; codecs="opus"', ';rate=16000') from a MIME type.
    Example: 'audio/webm;codecs=opus' -> 'audio/webm'
    """
    if not content_type:
        return ""
    return content_type.split(";")[0].strip().lower()


def detect_audio_container(audio_bytes: bytes) -> Optional[str]:
    """
    Inspects magic bytes of raw audio stream to detect genuine container format.
    Prevents false relabeling of audio streams (e.g. labeling WebM as WAV or vice versa).
    """
    if not audio_bytes or len(audio_bytes) < 4:
        return None
    # WebM / Matroska (EBML header element ID 0x1A45DFA3)
    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    # WAV / RIFF (RIFF header + WAVE format)
    if audio_bytes.startswith(b"RIFF") and len(audio_bytes) >= 12 and audio_bytes[8:12] == b"WAVE":
        return "wav"
    # OGG container (OggS)
    if audio_bytes.startswith(b"OggS"):
        return "ogg"
    # FLAC (fLaC)
    if audio_bytes.startswith(b"fLaC"):
        return "flac"
    # MP3 (ID3 tag or MPEG frame sync)
    if audio_bytes.startswith(b"ID3") or (audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
        return "mp3"
    # MP4 / M4A (ftyp box at byte 4)
    if len(audio_bytes) >= 8 and audio_bytes[4:8] == b"ftyp":
        return "mp4"
    return None


def resolve_audio_file_and_content_type(
    audio_bytes: bytes,
    filename: str = "recording.webm",
    content_type: str = "audio/webm",
) -> Tuple[str, str]:
    """
    Resolves a clean, consistent (filename, content_type) pair for Sarvam AI multipart upload.
    - Strips MIME parameters (e.g. ';codecs=opus' -> 'audio/webm')
    - Verifies container format using magic bytes to prevent mislabeling
    - Ensures filename extension matches the genuine MIME type
    """
    base_mime = normalize_mime_type(content_type)
    detected_format = detect_audio_container(audio_bytes)

    raw_name = os.path.splitext(filename or "recording")[0] or "recording"
    raw_ext = os.path.splitext(filename or "")[1].lower()

    # 1. Primary: Use genuine binary container format if detected
    if detected_format == "webm":
        return f"{raw_name}.webm", "audio/webm"
    elif detected_format == "wav":
        return f"{raw_name}.wav", "audio/wav"
    elif detected_format == "ogg":
        return f"{raw_name}.ogg", "audio/ogg"
    elif detected_format == "mp3":
        return f"{raw_name}.mp3", "audio/mpeg"
    elif detected_format == "flac":
        return f"{raw_name}.flac", "audio/flac"
    elif detected_format == "mp4":
        return f"{raw_name}.mp4", "audio/mp4"

    # 2. Secondary: If binary container is chunked/unrecognized, use clean base MIME
    if base_mime in ("audio/webm", "video/webm") or raw_ext == ".webm":
        return f"{raw_name}.webm", "audio/webm"
    elif base_mime in ("audio/wav", "audio/x-wav", "audio/wave") or raw_ext == ".wav":
        return f"{raw_name}.wav", "audio/wav"
    elif base_mime in ("audio/ogg", "application/ogg") or raw_ext == ".ogg":
        return f"{raw_name}.ogg", "audio/ogg"
    elif base_mime in ("audio/mpeg", "audio/mp3") or raw_ext in (".mp3", ".mpeg"):
        return f"{raw_name}.mp3", "audio/mpeg"
    elif base_mime in ("audio/mp4", "audio/x-m4a", "video/mp4") or raw_ext in (".mp4", ".m4a"):
        return f"{raw_name}.mp4", "audio/mp4"
    elif base_mime in ("audio/flac", "audio/x-flac") or raw_ext == ".flac":
        return f"{raw_name}.flac", "audio/flac"
    elif base_mime and base_mime != "application/octet-stream":
        ext = raw_ext if raw_ext in (".webm", ".wav", ".ogg", ".mp3", ".mp4", ".flac") else ".webm"
        return f"{raw_name}{ext}", base_mime

    # 3. Default fallback
    return f"{raw_name}.webm", "audio/webm"


class SarvamSTTProvider(BaseSTTProvider):
    """
    Speech-to-Text provider powered by Sarvam AI's Saaras models:
    - saaras:v4 (latest, Indic languages + English, specialized for code-mixed speech)
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
        # Check explicit instance key first, then settings loaded from backend/.env
        key = (self._api_key or getattr(settings, "SARVAM_API_KEY", "") or "").strip()
        if not key and getattr(settings, "ENVIRONMENT", "") != "testing":
            # Guarantee direct read exclusively from backend/.env if not present in settings
            env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            sline = line.strip()
                            if sline.startswith("SARVAM_API_KEY="):
                                key = sline.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception as e:
                    logger.debug(f"Could not read .env for SARVAM_API_KEY: {e}")
        if not key:
            raise AIProviderError(
                "SARVAM_API_KEY is not configured on the backend. Please set SARVAM_API_KEY in backend/.env when STT_PROVIDER='sarvam'.",
                status_code=503,
                is_retryable=False,
            )
        return key

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

        # Resolve clean MIME type and filename, stripping codec parameters while validating genuine format
        clean_filename, clean_content_type = resolve_audio_file_and_content_type(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
        )

        headers = {
            "api-subscription-key": api_key,
        }

        # Sarvam multipart form parameters
        files = {
            "file": (clean_filename, audio_bytes, clean_content_type),
        }
        data: Dict[str, str] = {
            "model": model_name,
            "mode": mode,
            "language_code": lang_code,
        }

        # Keyterm prompting for saaras:v4 if prompt keywords are provided
        effective_prompt = (prompt or "").strip()
        if effective_prompt and model_name.startswith("saaras:v4"):
            terms = [t.strip() for t in re.split(r"[,;\n\.]+", effective_prompt) if t.strip() and len(t.strip()) <= 64]
            if terms:
                data["keyterms"] = json.dumps(terms[:50])

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

            if response.status_code in (401, 403):
                logger.error(f"Sarvam AI authentication failed ({response.status_code}): {response.text}")
                raise AIProviderError("Invalid SARVAM_API_KEY configured on server.", status_code=401)
            elif response.status_code == 429:
                logger.error(f"Sarvam AI rate limit reached: {response.text}")
                raise AIProviderError(
                    "Sarvam AI rate limit exceeded. Please try again shortly.",
                    status_code=429,
                    is_retryable=True,
                )
            elif response.status_code == 400:
                resp_text = response.text or ""
                resp_lower = resp_text.lower()
                if any(k in resp_lower for k in ("duration exceeds", "30 seconds", "limit of 30", "batch api")):
                    logger.warning(f"Sarvam AI 30-second duration limit exceeded: {resp_text}")
                    raise AIProviderError(
                        f"Sarvam audio duration exceeds 30-second limit: {resp_text}",
                        status_code=400,
                        is_retryable=False,
                    )
                logger.error(f"Sarvam AI bad request: {resp_text}")
                raise AIProviderError(
                    f"Sarvam AI transcription rejected audio: {resp_text}",
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
