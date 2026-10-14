from typing import Optional
from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Recognized speech transcript from Whisper")
    model: str = Field(default="whisper-large-v3-turbo", description="Model used for transcription")
    duration: Optional[float] = Field(default=None, description="Audio duration in seconds if available")
    language: str = Field(default="en", description="Detected or requested language code")
