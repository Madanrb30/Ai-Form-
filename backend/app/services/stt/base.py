from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseSTTProvider(ABC):
    """Abstract Base Class for Speech-to-Text Providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'groq' or 'sarvam')."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Active or configured STT model identifier."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "recording.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribes audio bytes into text.

        Returns:
            Dict containing:
                - text: str (transcribed speech text)
                - model: str (model name used)
                - duration: Optional[float] (audio duration in seconds)
                - language: str (detected or requested language)
                - provider: str (provider identifier, e.g. "groq" or "sarvam")
        """
        pass
