"""Bandit wrapper - Python security linting."""

import json
import logging
import sys

from app.schemas.finding import SEVERITY_ORDER, Finding, Origin, Severity
from app.schemas.source import Language
from app.static_analysis.base import Workspace, run_tool
from app.static_analysis.catalog import lookup_python_rule

logger = logging.getLogger(__name__)

TOOL_NAME = "bandit"

_BANDIT_SEVERITY: dict[str, Severity] = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

#: Import-level warnings ("you imported pickle") duplicate the call-site finding
#: and would inflate the false-positive rate without adding information.
_NOISY_TESTS = frozenset({"B403", "B404", "B405", "B406", "B407", "B410", "B411"})


async def analyse(workspace: Workspace) -> list[Finding]:
    targets = workspace.paths_for({Language.PYTHON.value})
    if not targets:
        return []

    _, stdout, _ = await run_tool(
        [
            sys.executable,
            "-m",
            "bandit",
            "-f",
            "json",
            "-q",
            *[str(path) for path in targets],
        ],
        cwd=workspace.root,
    )

    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("bandit produced unparseable output: %s", stdout[:200])
        return []

    findings = []
    for row in payload.get("results", []):
        finding = _to_finding(row, workspace)
        if finding is not None:
            findings.append(finding)
    return findings


def _to_finding(row: dict, workspace: Workspace) -> Finding | None:
    test_id = row.get("test_id")
    line = row.get("line_number")
    if not test_id or not line or test_id in _NOISY_TESTS:
        return None

    info = lookup_python_rule(test_id)
    line_range = row.get("line_range") or [line]

    # Prefer the catalog's severity, but let bandit escalate when it is more
    # certain than our static table.
    severity = info.severity
    reported = _BANDIT_SEVERITY.get(row.get("issue_severity", ""), Severity.LOW)
    if row.get("issue_confidence") == "HIGH" and reported == Severity.HIGH:
        severity = max(severity, reported, key=lambda s: SEVERITY_ORDER[s])

    cwe_id = (row.get("issue_cwe") or {}).get("id")

    return Finding(
        file_path=workspace.relative(row.get("filename", "")),
        line_start=line,
        line_end=max(line_range) if line_range else line,
        severity=severity,
        category=info.category,
        title=f"{test_id}: {row.get('test_name', '')}".strip(": "),
        explanation=row.get("issue_text", ""),
        owasp=info.owasp,
        cwe=f"CWE-{cwe_id}" if cwe_id else info.cwe,
        origin=Origin.STATIC,
        tool=TOOL_NAME,
        rule_id=test_id,
        confidence=0.9 if row.get("issue_confidence") == "HIGH" else 0.75,
    )
