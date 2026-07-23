"""Runs every applicable analyser and returns one merged finding list.

A missing tool degrades the review rather than failing it: `tools_skipped`
records what could not run so the report can be honest about coverage.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from app.schemas.finding import Finding
from app.schemas.source import SourceFile
from app.static_analysis import ast_tool, bandit_tool, eslint_tool, ruff_tool, secrets
from app.static_analysis.base import ToolUnavailable, materialise

logger = logging.getLogger(__name__)


@dataclass
class StaticAnalysisResult:
    findings: list[Finding] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)
    tools_skipped: list[str] = field(default_factory=list)


async def run_all(files: list[SourceFile]) -> StaticAnalysisResult:
    """Analyse `files` with every tool that applies to them."""
    result = StaticAnalysisResult()
    if not files:
        return result

    # In-process analysers need no workspace.
    result.findings.extend(secrets.analyse(files))
    result.tools_run.append(secrets.TOOL_NAME)
    result.findings.extend(ast_tool.analyse(files))
    result.tools_run.append(ast_tool.TOOL_NAME)

    with materialise(files) as workspace:
        subprocess_tools = (
            (ruff_tool.TOOL_NAME, ruff_tool.analyse(workspace)),
            (bandit_tool.TOOL_NAME, bandit_tool.analyse(workspace)),
            (eslint_tool.TOOL_NAME, eslint_tool.analyse(workspace)),
        )
        outcomes = await asyncio.gather(
            *(coro for _, coro in subprocess_tools), return_exceptions=True
        )

    for (name, _), outcome in zip(subprocess_tools, outcomes, strict=True):
        if isinstance(outcome, ToolUnavailable):
            logger.info("Analyser %s skipped: %s", name, outcome)
            result.tools_skipped.append(name)
            continue
        if isinstance(outcome, BaseException):
            logger.warning("Analyser %s failed: %s", name, outcome, exc_info=outcome)
            result.tools_skipped.append(name)
            continue
        result.findings.extend(outcome)
        result.tools_run.append(name)

    logger.info(
        "Static analysis produced %d findings across %d files (tools: %s)",
        len(result.findings),
        len(files),
        ", ".join(result.tools_run),
    )
    return result
