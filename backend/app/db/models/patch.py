"""Refactored file produced by the refactor agent."""

import pymongo
from beanie import Document, PydanticObjectId


class Patch(Document):
    review_id: PydanticObjectId
    user_id: PydanticObjectId
    file_path: str
    #: Full corrected file - what the PDF calls `refactored_code`.
    refactored_code: str
    unified_diff: str
    #: Number of findings this patch was asked to address.
    addresses_findings: int = 0
    #: True only when the patched code re-parsed and re-linted cleanly.
    validated: bool = False
    validation_output: str = ""

    class Settings:
        name = "patches"
        indexes = [
            pymongo.IndexModel(
                [("review_id", pymongo.ASCENDING), ("file_path", pymongo.ASCENDING)],
                unique=True,
            ),
        ]
