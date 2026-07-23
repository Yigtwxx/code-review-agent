#!/usr/bin/env python3
"""CI client: send a pull request's changed files for review, gate the merge.

Runs inside GitHub Actions with the repository already checked out. It signs in
as a normal user - no separate trust path - starts a review, waits for it, then
writes the findings back as pull-request review comments and exits non-zero if
anything at or above the configured severity survived.

Depends only on the standard library so the workflow needs no install step.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

#: How long to wait for a review before giving up. A local model reviewing a
#: large pull request is not fast, and a CI job that fails on a timeout is
#: worse than one that waits.
DEFAULT_TIMEOUT_SECONDS = 1800
POLL_INTERVAL_SECONDS = 10


class CiError(RuntimeError):
    """Something went wrong that should fail the job loudly."""


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise CiError(f"{method} {url} failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise CiError(f"Cannot reach the review service at {url}: {exc}") from exc


def changed_files(base_sha: str, head_sha: str) -> list[dict[str, str]]:
    """Collect each changed file's content and its diff against the base."""
    names = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base_sha, head_sha],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    files: list[dict[str, str]] = []
    for name in names:
        try:
            with open(name, encoding="utf-8") as handle:
                content = handle.read()
        except (OSError, UnicodeDecodeError):
            continue  # binary, deleted, or unreadable - nothing to review

        patch = subprocess.run(
            ["git", "diff", "--unified=3", base_sha, head_sha, "--", name],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files.append({"path": name, "content": content, "patch": patch})
    return files


def wait_for_review(api: str, token: str, review_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        review = request_json(f"{api}/api/v1/reviews/{review_id}", token=token)
        if review["status"] in ("completed", "failed"):
            return review
        time.sleep(POLL_INTERVAL_SECONDS)
    raise CiError(f"Review did not finish within {timeout}s")


def post_pr_comments(
    repo: str, pr_number: int, findings: list[dict], commit_sha: str
) -> None:
    """Write findings back as a single pull-request review via `gh`."""
    if not findings:
        return

    comments = [
        {
            "path": finding["file_path"],
            "line": finding["line_start"],
            "side": "RIGHT",
            "body": _comment_body(finding),
        }
        for finding in findings
    ]

    payload = {
        "commit_id": commit_sha,
        "event": "COMMENT",
        "body": _summary_body(findings),
        "comments": comments,
    }

    result = subprocess.run(
        [
            "gh", "api", "--method", "POST",
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            "--input", "-",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A line the diff does not contain makes GitHub reject the whole
        # review; fall back to one plain comment so the findings are not lost.
        print(f"::warning::Inline review rejected: {result.stderr[:300]}")
        subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body-file", "-"],
            input=_summary_body(findings) + "\n\n" + _fallback_list(findings),
            text=True,
            check=False,
        )


def _comment_body(finding: dict) -> str:
    lines = [f"**{finding['severity'].upper()} · {finding['title']}**", ""]
    lines.append(finding["explanation"])

    tags = [t for t in (finding.get("owasp"), finding.get("cwe")) if t]
    if finding.get("corroborated_by"):
        tags.append(f"doğrulayan: {', '.join(finding['corroborated_by'])}")
    elif finding.get("origin") == "llm":
        tags.append("statik doğrulama yok")
    if tags:
        lines += ["", " · ".join(f"`{tag}`" for tag in tags)]

    if finding.get("suggested_fix"):
        lines += ["", "```suggestion", finding["suggested_fix"].rstrip(), "```"]

    agent = finding.get("agent") or finding.get("tool")
    if agent:
        lines += ["", f"<sub>{agent}</sub>"]
    return "\n".join(lines)


def _summary_body(findings: list[dict]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    breakdown = ", ".join(
        f"{counts[s]} {s}" for s in SEVERITY_ORDER if counts.get(s)
    )
    return f"### Code Review Agent\n\n{len(findings)} bulgu: {breakdown}"


def _fallback_list(findings: list[dict]) -> str:
    return "\n".join(
        f"- `{f['file_path']}:{f['line_start']}` **{f['severity']}** {f['title']}"
        for f in findings
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=os.environ.get("REVIEW_API_URL", ""))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument(
        "--fail-on",
        default="high",
        choices=list(SEVERITY_ORDER),
        help="Fail the job when a finding at or above this severity remains",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    email = os.environ.get("REVIEW_API_EMAIL", "")
    password = os.environ.get("REVIEW_API_PASSWORD", "")
    if not args.api or not email or not password:
        raise CiError(
            "REVIEW_API_URL, REVIEW_API_EMAIL and REVIEW_API_PASSWORD must be set"
        )

    token = request_json(
        f"{args.api}/api/v1/auth/login",
        method="POST",
        body={"email": email, "password": password},
    )["access_token"]

    files = changed_files(args.base_sha, args.head_sha)
    if not files:
        print("No changed files to review.")
        return 0
    print(f"Submitting {len(files)} changed files for review…")

    started = request_json(
        f"{args.api}/api/v1/reviews/ci",
        method="POST",
        token=token,
        body={
            "repo": args.repo,
            "pr_number": args.pr,
            "commit_sha": args.head_sha,
            "files": files,
        },
    )

    review = wait_for_review(args.api, token, started["id"], args.timeout)
    if review["status"] == "failed":
        raise CiError(f"Review failed: {review.get('error')}")

    findings = request_json(
        f"{args.api}/api/v1/reviews/{started['id']}/findings", token=token
    )
    open_findings = [f for f in findings if f["status"] == "open"]
    post_pr_comments(args.repo, args.pr, open_findings, args.head_sha)

    threshold = SEVERITY_ORDER[args.fail_on]
    blocking = [
        f for f in open_findings if SEVERITY_ORDER[f["severity"]] >= threshold
    ]

    print(f"{len(open_findings)} findings, risk score {review['risk_score']}.")
    for finding in blocking:
        print(
            f"::error file={finding['file_path']},line={finding['line_start']}::"
            f"{finding['severity']}: {finding['title']}"
        )

    if blocking:
        print(f"Failing: {len(blocking)} finding(s) at or above '{args.fail_on}'.")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CiError as error:
        print(f"::error::{error}")
        sys.exit(2)
