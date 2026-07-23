"""Review orchestration: persist, run the graph, persist the result.

The graph itself knows nothing about MongoDB. This module is the seam: it
stores the submission, runs the graph as a background task, and writes back
what came out. Keeping persistence here is what lets the benchmark harness and
the tests drive the same graph with no database at all.
"""

import logging
import time
from collections import Counter

from beanie import PydanticObjectId

from app.agents.graph import review_graph
from app.agents.llm import LlmUnavailable
from app.agents.state import PatchResult
from app.config import settings
from app.db.models import (
    FindingDoc,
    Patch,
    Review,
    ReviewFile,
    ReviewSource,
    ReviewStats,
    ReviewStatus,
    User,
)
from app.events.bus import EventType, emit
from app.schemas.finding import Finding
from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

#: LangGraph aborts a run that exceeds this many supersteps. Our graph is a
#: fixed pipeline, so this only ever trips on a bug.
RECURSION_LIMIT = 60


async def create_review(
    user: User, source: ReviewSource, files: list[SourceFile]
) -> Review:
    """Persist a submission and return the queued review."""
    review = Review(
        user_id=user.id,
        source=source,
        status=ReviewStatus.QUEUED,
        llm_model=user.preferences.llm_model or settings.llm_model,
    )
    await review.insert()

    await ReviewFile.insert_many(
        [
            ReviewFile(
                review_id=review.id,
                path=file.path,
                language=file.language,
                layers=file.layers,
                content=file.content,
                hunks=file.hunks,
                truncated=file.truncated,
            )
            for file in files
        ]
    )
    logger.info("Queued review %s with %d files", review.id, len(files))
    return review


async def run_review(review_id: PydanticObjectId) -> None:
    """Execute the graph for a queued review and store everything it produced.

    Runs as a background task; every exit path leaves the review in a terminal
    state, so a caller polling the document never waits forever.
    """
    review = await Review.get(review_id)
    if review is None:
        logger.warning("Review %s vanished before it could run", review_id)
        return

    stored = await ReviewFile.find(ReviewFile.review_id == review.id).to_list()
    files = [
        SourceFile(
            path=doc.path,
            content=doc.content,
            language=doc.language,
            layers=doc.layers,
            hunks=doc.hunks,
            truncated=doc.truncated,
        )
        for doc in stored
    ]

    review.status = ReviewStatus.RUNNING
    await review.save()
    await emit(
        str(review.id),
        EventType.REVIEW_STARTED,
        message=f"{len(files)} dosya, model {review.llm_model}",
        file_count=len(files),
        llm_model=review.llm_model,
    )

    started = time.perf_counter()
    try:
        result = await review_graph.ainvoke(
            {
                "review_id": str(review.id),
                "llm_model": review.llm_model,
                "files": files,
            },
            {"recursion_limit": RECURSION_LIMIT},
        )
    except LlmUnavailable as exc:
        await _fail(review, f"Yerel model kullanılamıyor: {exc}", started)
        return
    except Exception as exc:
        logger.exception("Review %s failed", review.id)
        await _fail(review, f"İnceleme sırasında hata: {exc}", started)
        return

    findings: list[Finding] = result.get("findings", [])
    patches: list[PatchResult] = result.get("patches", [])

    await _store_findings(review, findings)
    await _store_patches(review, patches)
    await _sync_layers(review, result.get("files", files))

    review.status = ReviewStatus.COMPLETED
    review.risk_score = result.get("risk_score", 0)
    review.stats = _build_stats(findings, files, result)
    review.duration_ms = int((time.perf_counter() - started) * 1000)
    review.finished_at = _now()
    await review.save()

    await emit(
        str(review.id),
        EventType.REVIEW_COMPLETED,
        message=f"{len(findings)} bulgu, risk skoru {review.risk_score}",
        risk_score=review.risk_score,
        finding_count=len(findings),
        duration_ms=review.duration_ms,
    )
    logger.info(
        "Review %s completed: %d findings in %dms",
        review.id,
        len(findings),
        review.duration_ms,
    )


async def _fail(review: Review, message: str, started: float) -> None:
    review.status = ReviewStatus.FAILED
    review.error = message
    review.duration_ms = int((time.perf_counter() - started) * 1000)
    review.finished_at = _now()
    await review.save()
    await emit(str(review.id), EventType.REVIEW_FAILED, message=message)


async def _store_findings(review: Review, findings: list[Finding]) -> None:
    if not findings:
        return
    await FindingDoc.insert_many(
        [
            FindingDoc.from_finding(
                finding, review_id=review.id, user_id=review.user_id
            )
            for finding in findings
        ]
    )


async def _store_patches(review: Review, patches: list[PatchResult]) -> None:
    if not patches:
        return
    await Patch.insert_many(
        [
            Patch(
                review_id=review.id,
                user_id=review.user_id,
                file_path=patch.file_path,
                refactored_code=patch.refactored_code,
                unified_diff=patch.unified_diff,
                addresses_findings=patch.addresses_findings,
                validated=patch.validated,
                validation_output=patch.validation_output,
            )
            for patch in patches
        ]
    )


async def _sync_layers(review: Review, files: list[SourceFile]) -> None:
    """Write back the layer assignment the partition node computed."""
    for file in files:
        if not file.layers:
            continue
        await ReviewFile.find(
            ReviewFile.review_id == review.id, ReviewFile.path == file.path
        ).update({"$set": {"layers": file.layers}})


def _build_stats(
    findings: list[Finding], files: list[SourceFile], result: dict
) -> ReviewStats:
    return ReviewStats(
        total_findings=len(findings),
        by_severity=dict(Counter(f.severity.value for f in findings)),
        by_layer=dict(Counter(f.layer.value for f in findings if f.layer)),
        by_origin=dict(Counter(f.origin.value for f in findings)),
        files_analysed=len(files),
        suppressed_low_confidence=result.get("suppressed_low_confidence", 0),
    )


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
