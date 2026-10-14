from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.models.user import UserRole


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
