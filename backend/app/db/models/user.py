"""User account document."""

from datetime import UTC, datetime

import pymongo
from beanie import Document
from pydantic import BaseModel, EmailStr, Field


class UserPreferences(BaseModel):
    """Per-user overrides applied when a review is started."""

    llm_model: str | None = None
    #: Findings below this severity are stored but hidden by default.
    min_severity: str = "low"


class User(Document):
    email: EmailStr
    password_hash: str
    display_name: str = ""
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    #: Fernet ciphertext, never the raw token.
    github_token_encrypted: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "users"
        indexes = [
            pymongo.IndexModel([("email", pymongo.ASCENDING)], unique=True),
        ]
