"""Schema the refactor agent is constrained to."""

from pydantic import BaseModel, Field


class RefactorResult(BaseModel):
    refactored_code: str = Field(
        description="The complete corrected file. No markdown fences, no prose."
    )
    notes: str = Field(
        default="",
        description="Short Turkish summary of what was changed and what was left",
    )
