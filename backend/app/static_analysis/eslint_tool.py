"""ESLint wrapper for JavaScript and TypeScript files.

Runs the pinned toolchain in `tools/eslint` rather than anything the submitted
code ships, so reviewed code is judged against a fixed ruleset. The toolchain
is optional: without `npm install` there, this analyser reports itself
unavailable and the review continues with the remaining tools.
"""

import json
import logging

from app.config import REPO_ROOT
from app.schemas.finding import Finding, Origin, Severity
from app.schemas.source import Language
from app.static_analysis.base import ToolUnavailable, Workspace, run_tool
from app.static_analysis.catalog import lookup_eslint_rule

logger = logging.getLogger(__name__)

TOOL_NAME = "eslint"

ESLINT_HOME = REPO_ROOT / "tools" / "eslint"
ESLINT_BIN = ESLINT_HOME / "node_modules" / "eslint" / "bin" / "eslint.js"
ESLINT_CONFIG = ESLINT_HOME / "eslint.config.mjs"

_LANGUAGES = {
    Language.TYPESCRIPT.value,
    Language.TSX.value,
    Language.JAVASCRIPT.value,
    Language.JSX.value,
}

#: ESLint numeric severity -> our floor. The catalog can raise it further.
_ESLINT_SEVERITY = {2: Severity.MEDIUM, 1: Severity.LOW}


async def analyse(workspace: Workspace) -> list[Finding]:
    targets = workspace.paths_for(_LANGUAGES)
    if not targets:
        return []
    if not ESLINT_BIN.exists():
        raise ToolUnavailable(
            f"ESLint toolchain missing; run `npm install` in {ESLINT_HOME}"
        )

    # ESLint 9 treats the config file's directory as the base path and refuses
    # to lint anything outside it. Dropping a re-export shim in the workspace
    # makes the workspace the base path, while plugins still resolve from
    # tools/eslint where they are actually installed.
    shim = workspace.root / "eslint.config.mjs"
    shim.write_text(
        f"export {{ default }} from {ESLINT_CONFIG.as_uri()!r};\n", encoding="utf-8"
    )

    _, stdout, stderr = await run_tool(
        [
            "node",
            str(ESLINT_BIN),
            "--format",
            "json",
            *[str(path) for path in targets],
        ],
        cwd=workspace.root,
    )

    try:
        reports = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        logger.warning("eslint produced unparseable output: %s", stderr[:300])
        return []

    findings: list[Finding] = []
    for report in reports:
        path = workspace.relative(report.get("filePath", ""))
        for message in report.get("messages", []):
            finding = _to_finding(path, message)
            if finding is not None:
                findings.append(finding)
    return findings


def _to_finding(path: str, message: dict) -> Finding | None:
    rule_id = message.get("ruleId")
    line = message.get("line")
    if line is None:
        return None
    if rule_id is None:
        # Parse errors carry no rule; report them so a broken file is visible.
        return Finding(
            file_path=path,
            line_start=line,
            line_end=line,
            severity=Severity.MEDIUM,
            category="parse-error",
            title="ESLint could not parse this file",
            explanation=message.get("message", ""),
            origin=Origin.STATIC,
            tool=TOOL_NAME,
            rule_id="parse-error",
            confidence=0.9,
        )

    info = lookup_eslint_rule(rule_id)
    reported = _ESLINT_SEVERITY.get(message.get("severity", 1), Severity.LOW)
    # The catalog knows which rules are genuinely security-critical; a rule it
    # rates highly keeps that rating even when ESLint only warns.
    severity = info.severity if info.owasp or info.cwe else reported

    return Finding(
        file_path=path,
        line_start=line,
        line_end=message.get("endLine") or line,
        severity=severity,
        category=info.category,
        title=f"{rule_id}",
        explanation=message.get("message", ""),
        owasp=info.owasp,
        cwe=info.cwe,
        origin=Origin.STATIC,
        tool=TOOL_NAME,
        rule_id=rule_id,
        confidence=0.9,
    )
