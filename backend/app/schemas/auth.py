from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4)
    full_name: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    avatar: str


class AuthTokenResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    user: UserResponse
