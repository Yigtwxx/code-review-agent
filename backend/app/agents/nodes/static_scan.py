"""Run every deterministic analyser before any model sees the code.

Order matters: static results are handed to the agents as ground truth, which
is what turns "the model thinks there is SQL injection here" into "Bandit B608
and the model agree on line 31".
"""

import logging

from app.agents.state import ReviewState
from app.events.bus import EventType, emit
from app.static_analysis.registry import run_all

logger = logging.getLogger(__name__)

STAGE = "static_scan"


async def static_scan(state: ReviewState) -> dict:
    review_id = state["review_id"]
    files = state["files"]

    # Benchmark-only escape hatch: measure the LLM without any static evidence.
    # Never set in production, where hybrid cross-validation is mandatory.
    if state.get("disable_static"):
        await emit(
            review_id,
            EventType.NODE_FINISHED,
            stage=STAGE,
            message="statik analiz devre dışı (benchmark)",
            tools_run=[],
            tools_skipped=[],
            finding_count=0,
        )
        return {
            "static_findings": [],
            "static_tools_run": [],
            "static_tools_skipped": [],
        }

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=STAGE,
        message=f"{len(files)} dosya statik analizden geçiriliyor",
    )

    result = await run_all(files)

    if result.tools_skipped:
        logger.info("Static analysers skipped: %s", ", ".join(result.tools_skipped))

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=f"{len(result.findings)} statik bulgu",
        tools_run=result.tools_run,
        tools_skipped=result.tools_skipped,
        finding_count=len(result.findings),
    )

    return {
        "static_findings": result.findings,
        "static_tools_run": result.tools_run,
        "static_tools_skipped": result.tools_skipped,
    }
