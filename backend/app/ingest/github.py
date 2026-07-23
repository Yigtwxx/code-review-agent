"""Fetch a pull request's changed files from the GitHub API.

The agents need the whole file for context but should only comment on what the
pull request changed, so each file arrives with both its full content and the
set of lines the patch touched.
"""

import logging
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.ingest.detect import detect_language, should_skip
from app.ingest.diff import parse_patch
from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

_PR_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)"
    r"/pull/(?P<number>\d+)"
)

#: Statuses whose new-file content we cannot or should not review.
_SKIP_STATUSES = frozenset({"removed", "renamed"})


class GitHubError(RuntimeError):
    """The pull request could not be fetched."""


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int

    @property
    def label(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_pr_url(url: str) -> PullRequestRef:
    match = _PR_URL.match(url.strip())
    if match is None:
        raise GitHubError(
            "Expected a pull request URL like https://github.com/owner/repo/pull/123"
        )
    return PullRequestRef(
        owner=match["owner"], repo=match["repo"], number=int(match["number"])
    )


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    effective = token or settings.github_token
    if effective:
        headers["Authorization"] = f"Bearer {effective}"
    return headers


async def fetch_pull_request(
    ref: PullRequestRef, *, token: str | None = None
) -> tuple[list[SourceFile], str]:
    """Return the reviewable files of a pull request and its head SHA."""
    headers = _headers(token)
    base = f"{settings.github_api_url}/repos/{ref.owner}/{ref.repo}"

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        pull = await _get_json(client, f"{base}/pulls/{ref.number}")
        head_sha = pull.get("head", {}).get("sha", "")

        changed = await _get_json(
            client,
            f"{base}/pulls/{ref.number}/files",
            params={"per_page": min(settings.max_files_per_review, 100)},
        )

        files: list[SourceFile] = []
        for entry in changed:
            source = await _to_source_file(client, entry)
            if source is not None:
                files.append(source)
            if len(files) >= settings.max_files_per_review:
                break

    if not files:
        raise GitHubError(
            "This pull request changes no files we can review "
            "(binary, generated or unsupported languages only)"
        )
    return files, head_sha


async def _to_source_file(client: httpx.AsyncClient, entry: dict) -> SourceFile | None:
    path = entry.get("filename", "")
    if entry.get("status") in _SKIP_STATUSES or should_skip(path):
        return None

    language = detect_language(path)
    patch = entry.get("patch")
    if language is None or not patch:
        # No patch means GitHub judged the diff too large or binary.
        return None

    raw_url = entry.get("raw_url")
    if not raw_url:
        return None

    try:
        response = await client.get(raw_url, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Could not fetch %s: %s", path, exc)
        return None

    content = response.text
    truncated = len(content.encode()) > settings.max_file_bytes
    if truncated:
        content = content.encode()[: settings.max_file_bytes].decode(
            "utf-8", errors="ignore"
        )

    return SourceFile(
        path=path,
        content=content,
        language=language,
        hunks=parse_patch(patch),
        truncated=truncated,
    )


async def _get_json(client: httpx.AsyncClient, url: str, **kwargs):
    try:
        response = await client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise GitHubError(f"GitHub is unreachable: {exc}") from exc

    if response.status_code == 404:
        raise GitHubError(
            "Pull request not found. A private repository needs a GitHub token "
            "in your settings."
        )
    if response.status_code in (401, 403):
        raise GitHubError(
            "GitHub refused the request (rate limit or insufficient token scope)."
        )
    if not response.is_success:
        raise GitHubError(f"GitHub returned {response.status_code}")
    return response.json()
