import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Invalid email address")
        return email


class RegisterInput(LoginInput):
    password: str = Field(min_length=8, max_length=256)


class AuthConfig(BaseModel):
    registration_enabled: bool


class UserView(BaseModel):
    id: str
    email: str
    is_admin: bool
    enabled: bool
    rpm_limit: int
    token_limit: int | None
    created_at: datetime


class AdminUserView(UserView):
    allowed_model_ids: list[str]
    active_keys: int
    total_tokens: int
    requests_count: int


class AdminUserUpdate(BaseModel):
    enabled: bool
    rpm_limit: int = Field(ge=1, le=10_000)
    token_limit: int | None = Field(default=None, ge=1)
    model_ids: list[str] = Field(default_factory=list, max_length=500)
    password: str | None = Field(default=None, min_length=8, max_length=256)


class AdminUserCreate(RegisterInput):
    enabled: bool = True
    rpm_limit: int = Field(default=30, ge=1, le=10_000)
    token_limit: int | None = Field(default=None, ge=1)
    model_ids: list[str] = Field(default_factory=list, max_length=500)


class SessionOutput(BaseModel):
    token: str
    user: UserView
