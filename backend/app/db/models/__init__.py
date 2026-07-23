"""Beanie document models.

`DOCUMENT_MODELS` is the single registry consumed by `init_beanie`; adding a
model here is all that is needed for its indexes to be created at startup.
"""

from app.db.models.finding import FindingDoc
from app.db.models.patch import Patch
from app.db.models.review import (
    Review,
    ReviewFile,
    ReviewSource,
    ReviewStats,
    ReviewStatus,
    SourceKind,
)
from app.db.models.user import User, UserPreferences

DOCUMENT_MODELS = (User, Review, ReviewFile, FindingDoc, Patch)

__all__ = [
    "DOCUMENT_MODELS",
    "FindingDoc",
    "Patch",
    "Review",
    "ReviewFile",
    "ReviewSource",
    "ReviewStats",
    "ReviewStatus",
    "SourceKind",
    "User",
    "UserPreferences",
]
