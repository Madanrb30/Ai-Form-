from typing import Optional
from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Recognized speech transcript")
    model: str = Field(default="whisper-large-v3-turbo", description="Model used for transcription")
    duration: Optional[float] = Field(default=None, description="Audio duration in seconds if available")
    language: str = Field(default="en", description="Detected or requested language code")
    provider: str = Field(default="groq", description="STT provider used ('groq' or 'sarvam')")
    fallback_used: Optional[bool] = Field(default=False, description="Whether fallback provider was utilized")
    fallback_reason: Optional[str] = Field(default=None, description="Reason fallback provider was utilized")
