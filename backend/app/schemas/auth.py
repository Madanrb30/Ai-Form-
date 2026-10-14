from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="Password must be between 8 and 128 characters")
    full_name: Optional[str] = Field(default=None, max_length=100)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)



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
