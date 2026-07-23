"""Drive the review pipeline for one benchmark case.

Three modes map onto the report's three configurations:

* ``static`` - the deterministic analysers alone (no model, no graph).
* ``llm``    - the full graph with ``disable_static`` set, so the model reviews
               with no static evidence and nothing to corroborate against.
* ``hybrid`` - the production graph: static evidence feeds the agents and
               cross-validates their claims.

The graph is invoked with no database, exactly like ``services.reviews`` does
in production but without the persistence around it.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.agents.graph import review_graph
from app.agents.state import PatchResult
from app.ingest.loader import load_file
from app.schemas.finding import Finding
from app.schemas.source import SourceFile
from app.static_analysis.registry import run_all

#: Matches app.services.reviews.RECURSION_LIMIT - deep enough for the two
#: fan-outs plus their branches.
RECURSION_LIMIT = 60


def load_paths(root: Path, rel_paths: list[str]) -> list[SourceFile]:
    """Load a specific subset of files under `root`, preserving relative paths."""
    files: list[SourceFile] = []
    for rel in rel_paths:
        source = load_file(root / rel, base=root)
        if source is None:
            raise FileNotFoundError(f"{rel} under {root} is not a reviewable file")
        files.append(source)
    return files


class GraphOutcome:
    """Findings, patches and wall-clock time for one graph invocation."""

    def __init__(
        self,
        findings: list[Finding],
        patches: list[PatchResult],
        risk_score: int,
        suppressed: int,
        latency_ms: int,
    ) -> None:
        self.findings = findings
        self.patches = patches
        self.risk_score = risk_score
        self.suppressed = suppressed
        self.latency_ms = latency_ms


async def run_graph(
    model: str, files: list[SourceFile], *, disable_static: bool
) -> GraphOutcome:
    """Invoke the compiled graph once and time it end to end."""
    started = time.perf_counter()
    result = await review_graph.ainvoke(
        {
            "review_id": f"bench-{model}-{len(files)}",
            "llm_model": model,
            "files": files,
            "disable_static": disable_static,
        },
        {"recursion_limit": RECURSION_LIMIT},
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return GraphOutcome(
        findings=result.get("findings", []),
        patches=result.get("patches", []),
        risk_score=result.get("risk_score", 0),
        suppressed=result.get("suppressed_low_confidence", 0),
        latency_ms=latency_ms,
    )


async def run_static_only(files: list[SourceFile]) -> GraphOutcome:
    """Run just the deterministic analysers - no model, no graph."""
    started = time.perf_counter()
    result = await run_all(files)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return GraphOutcome(
        findings=result.findings,
        patches=[],
        risk_score=0,
        suppressed=0,
        latency_ms=latency_ms,
    )
