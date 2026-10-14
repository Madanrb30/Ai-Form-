from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class SubmissionCreate(BaseModel):
    response_json: Dict[str, Any] = Field(..., description="Key-value mapping of field names to user inputs")


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    form_id: int
    response_json: Dict[str, Any]
    created_at: datetime
