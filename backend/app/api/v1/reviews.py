"""Review endpoints.

Every read goes through `OwnedReview`, so a review belonging to another user is
unreachable no matter which sub-resource is asked for.
"""

import io
import logging
import zipfile
from collections import Counter
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.auth.crypto import decrypt_secret
from app.auth.deps import CurrentUser, OwnedReview
from app.config import settings
from app.db.models import (
    FindingDoc,
    Patch,
    Review,
    ReviewFile,
    ReviewSource,
    SourceKind,
)
from app.ingest import service as ingest
from app.ingest.detect import detect_language, should_skip
from app.ingest.diff import parse_patch
from app.schemas.review import (
    CiScanRequest,
    FileContentResponse,
    FindingResponse,
    FindingUpdate,
    PasteRequest,
    PatchResponse,
    PullRequestRequest,
    ReviewDetail,
    ReviewFileSummary,
    ReviewSummary,
)
from app.schemas.source import SourceFile
from app.services import reviews as service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])

#: Newest first, and capped - the dashboard paginates rather than scrolling.
DEFAULT_PAGE_SIZE = 30


async def _start(
    user: CurrentUser,
    background: BackgroundTasks,
    source: ReviewSource,
    files: list[SourceFile],
) -> ReviewSummary:
    review = await service.create_review(user, source, files)
    background.add_task(service.run_review, review.id)
    return _summary(review)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def create_from_upload(
    user: CurrentUser,
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File()],
) -> ReviewSummary:
    """Start a review from uploaded files or a ZIP archive."""
    try:
        sources = await ingest.from_uploads(files)
    except ingest.IngestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _start(
        user,
        background,
        ReviewSource(kind=SourceKind.UPLOAD, label=ingest.describe_upload(sources)),
        sources,
    )


@router.post("/paste", status_code=status.HTTP_202_ACCEPTED)
async def create_from_paste(
    user: CurrentUser, background: BackgroundTasks, body: PasteRequest
) -> ReviewSummary:
    """Start a review from a pasted snippet."""
    try:
        sources = ingest.from_paste(body.filename, body.content)
    except ingest.IngestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _start(
        user,
        background,
        ReviewSource(kind=SourceKind.PASTE, label=sources[0].path),
        sources,
    )


@router.post("/pull-request", status_code=status.HTTP_202_ACCEPTED)
async def create_from_pull_request(
    user: CurrentUser, background: BackgroundTasks, body: PullRequestRequest
) -> ReviewSummary:
    """Start a review of a GitHub pull request's changed lines."""
    token = (
        decrypt_secret(user.github_token_encrypted)
        if user.github_token_encrypted
        else None
    )
    try:
        sources, source = await ingest.from_pull_request(body.url, token=token)
    except ingest.IngestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _start(user, background, source, sources)


@router.post("/ci", status_code=status.HTTP_202_ACCEPTED)
async def create_from_ci(
    user: CurrentUser, background: BackgroundTasks, body: CiScanRequest
) -> ReviewSummary:
    """Start a review from files a CI job already has checked out.

    Same auth as every other endpoint: the workflow signs in with credentials
    from the repository's secrets, so a CI review belongs to a real account and
    obeys the same ownership rules.
    """
    sources: list[SourceFile] = []
    for entry in body.files:
        language = detect_language(entry.path)
        if language is None or should_skip(entry.path):
            continue
        sources.append(
            SourceFile(
                path=entry.path,
                content=entry.content,
                language=language,
                hunks=parse_patch(entry.patch) if entry.patch else None,
            )
        )

    if not sources:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No reviewable source files in this changeset",
        )

    label = (
        f"{body.repo}#{body.pr_number}"
        if body.pr_number is not None
        else f"{body.repo} (CI)"
    )
    return await _start(
        user,
        background,
        ReviewSource(
            kind=SourceKind.CI,
            label=label,
            repo=body.repo,
            pr_number=body.pr_number,
            commit_sha=body.commit_sha,
        ),
        sources[: settings.max_files_per_review],
    )


@router.get("")
async def list_reviews(
    user: CurrentUser, limit: int = DEFAULT_PAGE_SIZE, skip: int = 0
) -> list[ReviewSummary]:
    documents = (
        await Review.find(Review.user_id == user.id)
        .sort(-Review.created_at)
        .skip(max(skip, 0))
        .limit(min(max(limit, 1), 100))
        .to_list()
    )
    return [_summary(review) for review in documents]


@router.get("/{review_id}")
async def get_review(review: OwnedReview) -> ReviewDetail:
    files = await ReviewFile.find(ReviewFile.review_id == review.id).to_list()
    counts = Counter(
        doc.file_path
        for doc in await FindingDoc.find(FindingDoc.review_id == review.id).to_list()
    )
    return ReviewDetail(
        **_summary(review).model_dump(),
        files=[
            ReviewFileSummary(
                path=doc.path,
                language=doc.language,
                layers=doc.layers,
                line_count=doc.content.count("\n") + 1,
                truncated=doc.truncated,
                finding_count=counts.get(doc.path, 0),
            )
            for doc in sorted(files, key=lambda d: d.path)
        ],
    )


@router.get("/{review_id}/files/{path:path}")
async def get_file(review: OwnedReview, path: str) -> FileContentResponse:
    document = await ReviewFile.find_one(
        ReviewFile.review_id == review.id, ReviewFile.path == path
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found in this review")
    return FileContentResponse(
        path=document.path,
        language=document.language,
        layers=document.layers,
        content=document.content,
        hunks=document.hunks,
        truncated=document.truncated,
    )


@router.get("/{review_id}/findings")
async def list_findings(review: OwnedReview) -> list[FindingResponse]:
    documents = await FindingDoc.find(FindingDoc.review_id == review.id).to_list()
    documents.sort(key=lambda d: (d.file_path, d.line_start))
    return [_finding(document) for document in documents]


@router.patch("/{review_id}/findings/{finding_id}")
async def update_finding(
    review: OwnedReview, finding_id: PydanticObjectId, body: FindingUpdate
) -> FindingResponse:
    """Resolve or dismiss a finding."""
    document = await FindingDoc.find_one(
        FindingDoc.id == finding_id, FindingDoc.review_id == review.id
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    document.status = body.status
    await document.save()
    return _finding(document)


@router.get("/{review_id}/patches")
async def list_patches(review: OwnedReview) -> list[PatchResponse]:
    documents = await Patch.find(Patch.review_id == review.id).to_list()
    return [
        PatchResponse(
            file_path=doc.file_path,
            refactored_code=doc.refactored_code,
            unified_diff=doc.unified_diff,
            addresses_findings=doc.addresses_findings,
            validated=doc.validated,
            validation_output=doc.validation_output,
        )
        for doc in sorted(documents, key=lambda d: d.file_path)
    ]


@router.get("/{review_id}/download")
async def download_refactored(review: OwnedReview) -> StreamingResponse:
    """Download every refactored file as a ZIP archive."""
    patches = await Patch.find(Patch.review_id == review.id).to_list()
    if not patches:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This review produced no refactored files"
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for patch in patches:
            archive.writestr(patch.file_path, patch.refactored_code)
            archive.writestr(f"{patch.file_path}.patch", patch.unified_diff)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="refactored-{review.id}.zip"'
            )
        },
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(review: OwnedReview) -> None:
    await FindingDoc.find(FindingDoc.review_id == review.id).delete()
    await Patch.find(Patch.review_id == review.id).delete()
    await ReviewFile.find(ReviewFile.review_id == review.id).delete()
    await review.delete()


def _summary(review: Review) -> ReviewSummary:
    return ReviewSummary(
        id=str(review.id),
        status=review.status,
        source=review.source,
        llm_model=review.llm_model,
        risk_score=review.risk_score,
        stats=review.stats,
        error=review.error,
        duration_ms=review.duration_ms,
        created_at=review.created_at,
        finished_at=review.finished_at,
    )


def _finding(document: FindingDoc) -> FindingResponse:
    return FindingResponse(
        id=str(document.id),
        file_path=document.file_path,
        line_start=document.line_start,
        line_end=document.line_end,
        severity=document.severity.value,
        category=document.category,
        title=document.title,
        explanation=document.explanation,
        suggested_fix=document.suggested_fix,
        owasp=document.owasp,
        cwe=document.cwe,
        origin=document.origin.value,
        tool=document.tool,
        rule_id=document.rule_id,
        agent=document.agent,
        lens=document.lens.value if document.lens else None,
        layer=document.layer.value if document.layer else None,
        confidence=document.confidence,
        corroborated_by=document.corroborated_by,
        status=document.status,
    )
