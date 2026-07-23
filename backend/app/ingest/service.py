"""Turn whatever the user submitted into `SourceFile`s.

Three entry points - uploaded files, pasted code, a pull request URL - and one
output shape. Limits are enforced here, at the boundary, so no later stage has
to wonder whether it is holding a 400 MB file.
"""

import logging
from pathlib import PurePosixPath

from fastapi import UploadFile

from app.config import settings
from app.db.models import ReviewSource, SourceKind
from app.ingest.archive import ArchiveError, extract_source_files
from app.ingest.detect import detect_language, is_probably_binary, should_skip
from app.ingest.github import GitHubError, fetch_pull_request, parse_pr_url
from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

_ARCHIVE_SUFFIXES = (".zip",)


class IngestError(ValueError):
    """The submission cannot be reviewed as given."""


def _safe_path(name: str) -> str:
    """Strip any directory traversal a client may have put in a filename."""
    parts = [
        part
        for part in PurePosixPath(name.replace("\\", "/")).parts
        if part not in ("..", "/", ".")
    ]
    return "/".join(parts) or "submitted_file"


async def from_uploads(uploads: list[UploadFile]) -> list[SourceFile]:
    """Read uploaded files, expanding any ZIP archives."""
    files: list[SourceFile] = []
    budget = settings.max_upload_bytes

    for upload in uploads:
        raw = await upload.read()
        budget -= len(raw)
        if budget < 0:
            limit_mb = settings.max_upload_bytes // 1024 // 1024
            raise IngestError(f"Upload exceeds the {limit_mb} MB limit")

        name = _safe_path(upload.filename or "submitted_file")

        if name.lower().endswith(_ARCHIVE_SUFFIXES):
            try:
                files.extend(extract_source_files(raw))
            except ArchiveError as exc:
                raise IngestError(str(exc)) from exc
            continue

        if is_probably_binary(raw):
            continue
        if len(raw) > settings.max_file_bytes:
            raise IngestError(f"{name} is larger than the per-file limit")

        language = detect_language(name)
        if language is None or should_skip(name):
            continue

        files.append(
            SourceFile(
                path=name,
                content=raw.decode("utf-8", errors="replace"),
                language=language,
            )
        )

    if not files:
        raise IngestError(
            "No reviewable source files found. Supported: Python, "
            "JavaScript/TypeScript, SQL, YAML, Dockerfile and similar text files."
        )
    if len(files) > settings.max_files_per_review:
        files = files[: settings.max_files_per_review]
        logger.info("Truncated submission to %d files", settings.max_files_per_review)
    return files


def from_paste(filename: str, content: str) -> list[SourceFile]:
    """Wrap a pasted snippet as a single file."""
    if not content.strip():
        raise IngestError("Pasted content is empty")
    if len(content.encode()) > settings.max_file_bytes:
        raise IngestError("Pasted content is larger than the per-file limit")

    path = _safe_path(filename or "snippet.py")
    language = detect_language(path)
    if language is None:
        raise IngestError(
            f"Cannot determine a language for '{path}'. "
            "Give the file an extension such as .py, .ts or .sql."
        )
    return [SourceFile(path=path, content=content, language=language)]


async def from_pull_request(
    url: str, *, token: str | None = None
) -> tuple[list[SourceFile], ReviewSource]:
    """Fetch a pull request's changed files."""
    try:
        ref = parse_pr_url(url)
        files, head_sha = await fetch_pull_request(ref, token=token)
    except GitHubError as exc:
        raise IngestError(str(exc)) from exc

    source = ReviewSource(
        kind=SourceKind.PULL_REQUEST,
        label=ref.label,
        repo=f"{ref.owner}/{ref.repo}",
        pr_number=ref.number,
        commit_sha=head_sha,
    )
    return files, source


def describe_upload(files: list[SourceFile]) -> str:
    """Short label for the review list, e.g. 'app.py +3 dosya'."""
    if len(files) == 1:
        return files[0].path
    return f"{files[0].path} +{len(files) - 1} dosya"
