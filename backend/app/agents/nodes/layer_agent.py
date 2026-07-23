"""The layer agents - one branch per (layer, lens) pair.

LangGraph invokes this node once per `Send`, so `FrontendAgent · security` and
`BackendAgent · quality` run as independent parallel branches over the same
graph state. Each branch reviews only the files that belong to its layer, and
sees only its own lens's instructions.

Two guards keep model output honest before it becomes a finding:

* a cited line must actually exist in the chunk the model was shown, and
* in pull-request mode the line must be one the pull request changed.

Both are counted rather than silently dropped - a model that cites lines it was
never shown is information about the model.
"""

import logging

from app.agents.chunking import Chunk, chunk_file
from app.agents.llm import LlmUnavailable, structured
from app.agents.state import AgentTask
from app.events.bus import EventType, emit
from app.prompts import render
from app.schemas.finding import Finding, Layer, Lens, LlmFinding, LlmFindingList, Origin
from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

AGENT_LABELS: dict[Layer, str] = {
    Layer.FRONTEND: "FrontendAgent",
    Layer.BACKEND: "BackendAgent",
    Layer.DATABASE: "DatabaseAgent",
    Layer.CONFIG_INFRA: "ConfigAgent",
    Layer.GENERIC: "GenericAgent",
}


def agent_label(layer: Layer, lens: Lens) -> str:
    return f"{AGENT_LABELS[layer]} · {lens.value}"


async def layer_agent(task: AgentTask) -> dict:
    layer: Layer = task["layer"]
    lens: Lens = task["lens"]
    review_id = task["review_id"]
    stage = agent_label(layer, lens)

    system = render(f"personas/{layer.value}.jinja2", lens=lens.value)

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=stage,
        message=f"{len(task['files'])} dosya inceleniyor",
        layer=layer.value,
        lens=lens.value,
    )

    findings: list[Finding] = []
    rejected = 0

    for file in task["files"]:
        for chunk in chunk_file(file):
            try:
                emitted = await _review_chunk(task, file, chunk, system)
            except LlmUnavailable:
                # No model, no review: fail loudly rather than reporting an
                # empty result that looks like a clean bill of health.
                raise
            except Exception as exc:
                logger.warning(
                    "%s failed on %s:%s-%s: %s",
                    stage,
                    file.path,
                    chunk.line_start,
                    chunk.line_end,
                    exc,
                )
                continue

            for finding in emitted:
                accepted = _validate(finding, file, chunk)
                if accepted is None:
                    rejected += 1
                    continue
                findings.append(accepted)
                await emit(
                    review_id,
                    EventType.FINDING,
                    stage=stage,
                    message=accepted.title,
                    file_path=accepted.file_path,
                    line_start=accepted.line_start,
                    severity=accepted.severity.value,
                    category=accepted.category,
                )

    if rejected:
        logger.info("%s: dropped %d findings citing invalid lines", stage, rejected)

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=stage,
        message=f"{len(findings)} bulgu",
        finding_count=len(findings),
        rejected_count=rejected,
    )

    return {"agent_findings": findings}


async def _review_chunk(
    task: AgentTask, file: SourceFile, chunk: Chunk, system: str
) -> list[Finding]:
    """One model call: build the prompt, parse the schema, tag provenance."""
    layer: Layer = task["layer"]
    lens: Lens = task["lens"]

    static_for_chunk = [
        {
            "line": item.line_start,
            "rule": item.rule_id or item.category,
            "tool": item.tool or "static",
            "message": item.explanation or item.title,
        }
        for item in task["static_findings"]
        if item.file_path == file.path
        and chunk.line_start <= item.line_start <= chunk.line_end
    ]

    changed = file.changed_lines
    user = render(
        "review_user.jinja2",
        path=file.path,
        language=file.language.value,
        layer=layer.value,
        lens=lens.value,
        numbered_code=chunk.numbered(file),
        static_findings=static_for_chunk,
        injection_lines=[
            line
            for line in task["injection_flags"].get(file.path, [])
            if chunk.line_start <= line <= chunk.line_end
        ],
        scope_lines=_format_scope(changed, chunk),
    )

    response = await structured(
        LlmFindingList, system=system, user=user, model=task["llm_model"]
    )
    return [_to_finding(item, file, layer, lens) for item in response.findings]


def _format_scope(changed: set[int] | None, chunk: Chunk) -> str:
    """Human-readable changed-line list for the prompt, or '' for full review."""
    if changed is None:
        return ""
    in_chunk = sorted(
        line for line in changed if chunk.line_start <= line <= chunk.line_end
    )
    if not in_chunk:
        return ""
    return ", ".join(str(line) for line in in_chunk)


def _to_finding(
    item: LlmFinding, file: SourceFile, layer: Layer, lens: Lens
) -> Finding:
    """Attach provenance the model is not allowed to assert about itself."""
    return Finding(
        file_path=file.path,
        line_start=item.line_start,
        line_end=max(item.line_start, item.line_end),
        severity=item.severity,
        category=item.category.value,
        title=item.title,
        explanation=item.explanation,
        suggested_fix=item.suggested_fix,
        cwe=item.cwe,
        origin=Origin.LLM,
        agent=AGENT_LABELS[layer],
        lens=lens,
        layer=layer,
        confidence=item.confidence,
    )


def _validate(finding: Finding, file: SourceFile, chunk: Chunk) -> Finding | None:
    """Drop findings anchored to lines the model was not shown."""
    if not chunk.line_start <= finding.line_start <= chunk.line_end:
        return None
    if finding.line_end > file.line_count:
        finding.line_end = finding.line_start

    changed = file.changed_lines
    if changed is not None and not any(
        line in changed for line in range(finding.line_start, finding.line_end + 1)
    ):
        # Pull-request mode: pre-existing problems are out of scope.
        return None
    return finding
