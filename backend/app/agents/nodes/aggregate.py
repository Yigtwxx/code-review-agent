"""Merge static and agent findings into one deduplicated list.

This is where the hybrid claim in the project brief is actually cashed in.
Findings about the same defect arrive from several directions - Bandit and Ruff
both know `B608`/`S608`, and the backend agent may describe the same injection
in prose. Clustering them means:

* the reviewer sees one comment per defect, not four;
* an agent finding that a deterministic tool independently confirms is marked
  `HYBRID` and gains confidence - it is no longer just a model's opinion;
* an agent finding that nothing corroborates keeps its own, lower confidence
  and is judged on that in the next node.

Clustering is by (file, category) with a small line tolerance, because a linter
points at the call and a model often points at the line above or below it.
"""

import logging
from collections import defaultdict

from app.agents.state import ReviewState
from app.events.bus import EventType, emit
from app.schemas.finding import (
    SECURITY_CATEGORIES,
    SEVERITY_ORDER,
    Finding,
    Lens,
    Origin,
)

logger = logging.getLogger(__name__)

STAGE = "aggregate"

#: Two reports of the same category within this many lines are one defect.
LINE_TOLERANCE = 3

#: Added to an agent finding's confidence when a deterministic tool agrees.
CORROBORATION_BONUS = 0.25


async def aggregate(state: ReviewState) -> dict:
    review_id = state["review_id"]
    static = state.get("static_findings", [])
    agent = state.get("agent_findings", [])

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=STAGE,
        message=f"{len(static)} statik + {len(agent)} ajan bulgusu birleştiriliyor",
    )

    merged = _merge([*static, *agent])
    merged.sort(key=lambda f: (f.file_path, f.line_start, -SEVERITY_ORDER[f.severity]))

    corroborated = sum(1 for f in merged if f.origin is Origin.HYBRID)
    logger.info(
        "Aggregated %d raw findings into %d (%d corroborated)",
        len(static) + len(agent),
        len(merged),
        corroborated,
    )

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=f"{len(merged)} benzersiz bulgu, {corroborated} çapraz doğrulandı",
        unique=len(merged),
        corroborated=corroborated,
    )

    return {"findings": merged}


def _merge(findings: list[Finding]) -> list[Finding]:
    grouped: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[(finding.file_path, finding.category)].append(finding)

    merged: list[Finding] = []
    for group in grouped.values():
        for cluster in _cluster_by_line(group):
            merged.append(_combine(cluster))
    return merged


def _cluster_by_line(group: list[Finding]) -> list[list[Finding]]:
    """Split same-category findings in a file into per-defect clusters.

    Clusters on range *overlap*, not just proximity of the first line: a linter
    points at the offending statement while an agent often reports the whole
    enclosing function. Those are one defect, and comparing only `line_start`
    would file them as two.
    """
    ordered = sorted(group, key=lambda f: (f.line_start, f.line_end))
    clusters: list[list[Finding]] = []
    spans: list[tuple[int, int]] = []

    for finding in ordered:
        if spans and finding.line_start <= spans[-1][1] + LINE_TOLERANCE:
            clusters[-1].append(finding)
            spans[-1] = (spans[-1][0], max(spans[-1][1], finding.line_end))
        else:
            clusters.append([finding])
            spans.append((finding.line_start, finding.line_end))
    return clusters


def _attribution_rank(finding: Finding) -> tuple[int, float]:
    """Rank candidates for whose write-up represents the merged finding.

    Several agents legitimately spot the same defect - a quality lens will
    still notice an obvious RCE. Attributing it to `DatabaseAgent · quality`
    when `BackendAgent · security` also reported it is misleading provenance,
    so the lens that matches the finding's nature wins ties.
    """
    matches_lens = (finding.category in SECURITY_CATEGORIES) == (
        finding.lens is Lens.SECURITY
    )
    return (1 if matches_lens else 0, finding.confidence)


def _combine(cluster: list[Finding]) -> Finding:
    """Fold one cluster into a single finding, preserving the best of each."""
    if len(cluster) == 1:
        return cluster[0]

    static_members = [f for f in cluster if f.origin is Origin.STATIC]
    llm_members = [f for f in cluster if f.origin is not Origin.STATIC]

    # The agent's write-up is the more useful comment; the tool's rule id is
    # the more useful evidence. Keep both.
    base = (
        max(llm_members, key=_attribution_rank)
        if llm_members
        else max(static_members, key=lambda f: SEVERITY_ORDER[f.severity])
    ).model_copy(deep=True)

    base.severity = max(cluster, key=lambda f: SEVERITY_ORDER[f.severity]).severity
    base.line_start = min(f.line_start for f in cluster)
    base.line_end = max(f.line_end for f in cluster)

    rule_ids = sorted(
        {f"{f.tool}:{f.rule_id}" for f in static_members if f.tool and f.rule_id}
    )

    if llm_members and static_members:
        base.origin = Origin.HYBRID
        base.corroborated_by = rule_ids
        base.confidence = min(0.99, base.confidence + CORROBORATION_BONUS)
        # Keep the tool attribution so the UI can show "Bandit B608 agrees".
        base.tool = static_members[0].tool
        base.rule_id = static_members[0].rule_id
    elif static_members:
        base.corroborated_by = [
            r for r in rule_ids if r != f"{base.tool}:{base.rule_id}"
        ]

    base.owasp = base.owasp or next((f.owasp for f in cluster if f.owasp), None)
    base.cwe = base.cwe or next((f.cwe for f in cluster if f.cwe), None)
    base.suggested_fix = base.suggested_fix or next(
        (f.suggested_fix for f in cluster if f.suggested_fix), None
    )
    return base
