"""Pure metric functions - no I/O, no model calls, fully unit-testable.

Detection matches a produced finding to a labeled defect when the category slug
is identical AND the line ranges overlap within a tolerance (default +/-3
lines, per docs/sonuc-raporu.md). Category equality is deliberate: a finding
that spots the right line but calls SQL injection "code injection" is a
different, weaker result and is not counted as a hit.
"""

from __future__ import annotations

from collections import Counter

from app.agents.state import PatchResult
from app.schemas.finding import Finding, Severity
from benchmarks.schema import DetectionResult, GroundTruthDefect

#: Severities that must never appear on a clean sample; each one is a false
#: positive when it does.
FALSE_POSITIVE_SEVERITIES: frozenset[Severity] = frozenset(
    {Severity.CRITICAL, Severity.HIGH}
)


def _overlaps(finding: Finding, defect: GroundTruthDefect, tolerance: int) -> bool:
    """True when the finding's line span is within `tolerance` of the defect's."""
    return (
        finding.line_start <= defect.line_end + tolerance
        and finding.line_end >= defect.line_start - tolerance
    )


def matches(finding: Finding, defect: GroundTruthDefect, tolerance: int = 3) -> bool:
    return finding.category == defect.category and _overlaps(finding, defect, tolerance)


def detection(
    findings: list[Finding],
    defects: list[GroundTruthDefect],
    tolerance: int = 3,
) -> DetectionResult:
    """How many labeled defects were found with the right category and line."""
    missed: list[str] = []
    matched = 0
    for defect in defects:
        if any(matches(f, defect, tolerance) for f in findings):
            matched += 1
        else:
            missed.append(f"{defect.category}@{defect.line_start}")
    return DetectionResult(matched=matched, total=len(defects), missed=missed)


def false_positives(findings: list[Finding]) -> int:
    """Count of critical/high findings - on a clean sample these are all wrong."""
    return sum(1 for f in findings if f.severity in FALSE_POSITIVE_SEVERITIES)


def fix_accuracy(patches: list[PatchResult]) -> tuple[int, int]:
    """(validated, total) - the ratio of patches that survived re-scanning."""
    validated = sum(1 for p in patches if p.validated)
    return validated, len(patches)


def origin_breakdown(findings: list[Finding]) -> dict[str, int]:
    """Count findings by provenance (static / llm / hybrid)."""
    return dict(Counter(f.origin.value for f in findings))
