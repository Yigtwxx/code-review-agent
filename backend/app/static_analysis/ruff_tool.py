"""Ruff wrapper (lint + flake8-bandit security rules) for Python files."""

import json
import logging
import sys

from app.schemas.finding import Finding, Origin
from app.schemas.source import Language
from app.static_analysis.base import Workspace, run_tool
from app.static_analysis.catalog import lookup_python_rule

logger = logging.getLogger(__name__)

TOOL_NAME = "ruff"

#: `S` is flake8-bandit; the rest cover correctness and maintainability.
#: `--isolated` ignores any pyproject the submission ships, so results are
#: reproducible rather than dependent on the reviewed project's own config.
SELECTED_RULES = "E,F,B,S,SIM,UP,C90"


async def analyse(workspace: Workspace) -> list[Finding]:
    targets = workspace.paths_for({Language.PYTHON.value})
    if not targets:
        return []

    _, stdout, _ = await run_tool(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--select",
            SELECTED_RULES,
            "--output-format",
            "json",
            *[str(path) for path in targets],
        ],
        cwd=workspace.root,
    )

    try:
        rows = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        logger.warning("ruff produced unparseable output: %s", stdout[:200])
        return []

    return [finding for row in rows if (finding := _to_finding(row, workspace))]


def _to_finding(row: dict, workspace: Workspace) -> Finding | None:
    rule_code = row.get("code")
    location = row.get("location") or {}
    line = location.get("row")
    if not rule_code or not line:
        return None

    info = lookup_python_rule(rule_code)
    end_line = (row.get("end_location") or {}).get("row") or line

    return Finding(
        file_path=workspace.relative(row.get("filename", "")),
        line_start=line,
        line_end=max(line, end_line),
        severity=info.severity,
        category=info.category,
        title=f"{rule_code}: {row.get('name', rule_code)}",
        explanation=row.get("message", ""),
        owasp=info.owasp,
        cwe=info.cwe,
        origin=Origin.STATIC,
        tool=TOOL_NAME,
        rule_id=rule_code,
        # Deterministic tools are trusted far more than the model.
        confidence=0.95,
    )
