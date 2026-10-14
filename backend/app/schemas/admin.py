from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field
from app.models.user import UserRole


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    suspended_users: int
    total_audit_logs: int
    users_by_role: Dict[str, int]
    total_forms: int = 0
    total_submissions: int = 0


class SystemHealthResponse(BaseModel):
    status: str
    project_name: str
    version: str
    environment: str
    database_status: str
    database_type: str
    ai_mode: str
    ai_provider: str
    ai_model: str
    transcription_model: str
    max_audio_size_mb: int
    jwt_algorithm: str
    token_expiry_hours: int


class UserAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    title: Optional[str] = None
    avatar: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: List[UserAdminResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class UserStatusUpdateRequest(BaseModel):
    is_active: bool
    reason: Optional[str] = Field(default=None, max_length=255)


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: Optional[int] = None
    actor_email: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    status: str
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    limit: int
    total_pages: int
