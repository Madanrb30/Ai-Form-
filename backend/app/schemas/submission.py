from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class SubmissionCreate(BaseModel):
    response_json: Dict[str, Any] = Field(..., description="Key-value mapping of field names to user inputs")


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    form_id: int
    response_json: Dict[str, Any]
    created_at: datetime


class UserSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    form_id: int
    form_title: str
    response_json: Dict[str, Any]
    created_at: datetime
    status: str = "Completed"
    generated_pdf_path: Optional[str] = None
    user_id: Optional[int] = None

