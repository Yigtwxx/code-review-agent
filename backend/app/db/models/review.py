"""Review run and its source files."""

from datetime import UTC, datetime
from enum import StrEnum

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

from app.schemas.source import DiffHunk, Language


class ReviewStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceKind(StrEnum):
    UPLOAD = "upload"
    PASTE = "paste"
    PULL_REQUEST = "pull_request"
    CI = "ci"


class ReviewSource(BaseModel):
    kind: SourceKind
    #: Human label shown in the UI, e.g. "vulnerable_api.py" or "owner/repo#42".
    label: str = ""
    repo: str | None = None
    pr_number: int | None = None
    commit_sha: str | None = None


class ReviewStats(BaseModel):
    total_findings: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_layer: dict[str, int] = Field(default_factory=dict)
    by_origin: dict[str, int] = Field(default_factory=dict)
    files_analysed: int = 0
    #: Findings the LLM raised that no static tool could corroborate and that
    #: fell below the confidence floor - our hallucination proxy metric.
    suppressed_low_confidence: int = 0


class Review(Document):
    user_id: PydanticObjectId
    source: ReviewSource
    status: ReviewStatus = ReviewStatus.QUEUED
    llm_model: str
    risk_score: int = 0
    stats: ReviewStats = Field(default_factory=ReviewStats)
    #: Populated when status is FAILED.
    error: str | None = None
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    class Settings:
        name = "reviews"
        indexes = [
            pymongo.IndexModel(
                [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]
            ),
        ]


class ReviewFile(Document):
    review_id: PydanticObjectId
    path: str
    language: Language
    layers: list[str] = Field(default_factory=list)
    content: str
    hunks: list[DiffHunk] | None = None
    truncated: bool = False
    #: Set by the injection guard when the file contains prompt-injection bait.
    injection_suspected: bool = False

    class Settings:
        name = "review_files"
        indexes = [
            pymongo.IndexModel(
                [("review_id", pymongo.ASCENDING), ("path", pymongo.ASCENDING)]
            ),
        ]
