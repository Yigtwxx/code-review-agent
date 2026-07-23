"""Request and response bodies for the review API."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import ReviewSource, ReviewStats, ReviewStatus
from app.schemas.finding import FindingStatus
from app.schemas.source import DiffHunk, Language


class PasteRequest(BaseModel):
    filename: str = Field(default="snippet.py", max_length=255)
    content: str = Field(min_length=1)


class PullRequestRequest(BaseModel):
    url: str = Field(description="https://github.com/owner/repo/pull/123")


class CiFile(BaseModel):
    path: str = Field(max_length=1024)
    content: str
    #: Unified diff for this file; when absent the whole file is reviewed.
    patch: str | None = None


class CiScanRequest(BaseModel):
    """A checkout that a CI job already has on disk.

    Authenticated as a normal user - the workflow logs in with credentials from
    the repository's secrets, so CI reviews land in that user's history and need
    no separate trust path.
    """

    repo: str = Field(max_length=255)
    pr_number: int | None = None
    commit_sha: str | None = Field(default=None, max_length=64)
    files: list[CiFile] = Field(min_length=1)


class ReviewSummary(BaseModel):
    """List-view projection: enough for a dashboard row, nothing more."""

    id: str
    status: ReviewStatus
    source: ReviewSource
    llm_model: str
    risk_score: int
    stats: ReviewStats
    error: str | None
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None


class ReviewFileSummary(BaseModel):
    path: str
    language: Language
    layers: list[str]
    line_count: int
    truncated: bool
    finding_count: int = 0


class ReviewDetail(ReviewSummary):
    files: list[ReviewFileSummary]


class FindingResponse(BaseModel):
    id: str
    file_path: str
    line_start: int
    line_end: int
    severity: str
    category: str
    title: str
    explanation: str
    suggested_fix: str | None
    owasp: str | None
    cwe: str | None
    origin: str
    tool: str | None
    rule_id: str | None
    agent: str | None
    lens: str | None
    layer: str | None
    confidence: float
    corroborated_by: list[str]
    status: FindingStatus


class FindingUpdate(BaseModel):
    status: FindingStatus


class FileContentResponse(BaseModel):
    path: str
    language: Language
    layers: list[str]
    content: str
    hunks: list[DiffHunk] | None
    truncated: bool


class PatchResponse(BaseModel):
    file_path: str
    refactored_code: str
    unified_diff: str
    addresses_findings: int
    validated: bool
    validation_output: str
