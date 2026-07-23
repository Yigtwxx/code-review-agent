"""Persisted review comment."""

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import Field

from app.schemas.finding import (
    Finding,
    FindingStatus,
    Layer,
    Lens,
    Origin,
    Severity,
)


class FindingDoc(Document):
    review_id: PydanticObjectId
    user_id: PydanticObjectId

    file_path: str
    line_start: int
    line_end: int

    severity: Severity
    category: str
    title: str
    explanation: str
    suggested_fix: str | None = None

    owasp: str | None = None
    cwe: str | None = None

    origin: Origin
    tool: str | None = None
    rule_id: str | None = None
    agent: str | None = None
    lens: Lens | None = None
    layer: Layer | None = None

    confidence: float = 0.5
    corroborated_by: list[str] = Field(default_factory=list)
    status: FindingStatus = FindingStatus.OPEN

    class Settings:
        name = "findings"
        indexes = [
            pymongo.IndexModel(
                [("review_id", pymongo.ASCENDING), ("file_path", pymongo.ASCENDING)]
            ),
            pymongo.IndexModel([("user_id", pymongo.ASCENDING)]),
        ]

    @classmethod
    def from_finding(
        cls,
        finding: Finding,
        *,
        review_id: PydanticObjectId,
        user_id: PydanticObjectId,
    ) -> "FindingDoc":
        return cls(
            review_id=review_id,
            user_id=user_id,
            **finding.model_dump(),
        )
