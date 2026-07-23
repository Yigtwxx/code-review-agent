"""Auth request/response bodies."""

from pydantic import BaseModel, EmailStr, Field

from app.db.models import UserPreferences


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    preferences: UserPreferences
    has_github_token: bool


class PreferencesUpdate(BaseModel):
    llm_model: str | None = None
    min_severity: str | None = None
    #: Plaintext on the way in; stored encrypted. Empty string clears it.
    github_token: str | None = None
