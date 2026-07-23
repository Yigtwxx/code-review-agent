"""Score the review and close it out.

Deliberately does not touch MongoDB. Keeping the graph free of persistence
means it can be run by the benchmark harness, or in a test, with no database -
storing the result is the caller's job.
"""

from collections import Counter

from app.agents.state import ReviewState
from app.events.bus import EventType, emit
from app.schemas.finding import SECURITY_CATEGORIES, SEVERITY_WEIGHT, Finding

STAGE = "report"

#: Risk is reported on a 0-100 scale; this caps the raw weighted sum.
MAX_RISK_SCORE = 100


def risk_score(findings: list[Finding]) -> int:
    """Weighted severity of the security findings, capped at 100."""
    total = sum(
        SEVERITY_WEIGHT[f.severity]
        for f in findings
        if f.category in SECURITY_CATEGORIES
    )
    return min(total, MAX_RISK_SCORE)


def summarise(findings: list[Finding]) -> dict[str, dict[str, int]]:
    return {
        "by_severity": dict(Counter(f.severity.value for f in findings)),
        "by_layer": dict(Counter(f.layer.value for f in findings if f.layer)),
        "by_origin": dict(Counter(f.origin.value for f in findings)),
    }


async def report(state: ReviewState) -> dict:
    review_id = state["review_id"]
    findings = state.get("findings", [])
    patches = state.get("patches", [])

    score = risk_score(findings)
    stats = summarise(findings)

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=f"{len(findings)} bulgu, risk skoru {score}",
        risk_score=score,
        patch_count=len(patches),
        validated_patches=sum(1 for p in patches if p.validated),
        **stats,
    )

    return {"risk_score": score}
