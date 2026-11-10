from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from .models import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # ADMIN is deliberately not self-assignable: admins come from the
    # ADMIN_EMAIL / ADMIN_PASSWORD bootstrap at service startup.
    role: Literal["ATTENDEE", "ORGANIZER"] = "ATTENDEE"
    phone: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    phone: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
