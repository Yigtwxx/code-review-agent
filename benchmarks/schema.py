"""Typed shapes for ground-truth labels and benchmark results.

Keeping these as Pydantic models means result files serialise to JSON for free
and the ground-truth loader validates category slugs against the app's closed
vocabulary at load time - a typo in the labels fails loudly instead of silently
scoring every finding as a miss.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.schemas.finding import Category, Severity

# Category is the closed vocabulary shared by the analysers and agents; the
# ground truth must speak the same language for detection matching to work.
_VALID_CATEGORIES = {c.value for c in Category}


class GroundTruthDefect(BaseModel):
    """One labeled defect: a category anchored to a line range in a file."""

    category: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: Severity = Severity.MEDIUM
    note: str = ""

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in _VALID_CATEGORIES:
            raise ValueError(
                f"ground-truth category {value!r} is not a known Category slug"
            )
        return value


class SampleTruth(BaseModel):
    language: str
    layer: str = ""
    defects: list[GroundTruthDefect]


class GroundTruth(BaseModel):
    """The whole label set, keyed by file path relative to the samples root."""

    description: str = ""
    line_tolerance: int = 3
    samples: dict[str, SampleTruth]

    @classmethod
    def load(cls, path: Path) -> GroundTruth:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def defects_for(self, file_paths: set[str]) -> list[GroundTruthDefect]:
        """Flatten the defects belonging to the given files."""
        return [
            defect
            for file_path, sample in self.samples.items()
            if file_path in file_paths
            for defect in sample.defects
        ]


class DetectionResult(BaseModel):
    matched: int
    total: int
    missed: list[str] = Field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.matched / self.total if self.total else 0.0


class CaseResult(BaseModel):
    """Outcome of one benchmark case - one (model, mode, group) invocation."""

    model: str
    mode: str  # static | llm | hybrid
    group: str  # e.g. "python", "typescript", "all"
    files: list[str]

    detection: DetectionResult | None = None
    false_positives: int | None = None  # critical/high count on clean input
    fix_total: int = 0
    fix_validated: int = 0
    finding_count: int = 0
    origin_counts: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = 0
    latency_ms_per_file: int = 0
    error: str = ""

    @property
    def fix_accuracy(self) -> float | None:
        return self.fix_validated / self.fix_total if self.fix_total else None


class BenchmarkReport(BaseModel):
    """The full result set written to disk and rendered into markdown tables."""

    generated_at: str = ""
    hardware: str = ""
    model_cases: list[CaseResult] = Field(default_factory=list)
    config_cases: list[CaseResult] = Field(default_factory=list)
