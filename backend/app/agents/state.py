"""Graph state and the payloads carried by fan-out branches."""

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel

from app.schemas.finding import Finding, Layer, Lens
from app.schemas.source import SourceFile


class PatchResult(BaseModel):
    """One refactored file, plus whether the result actually holds up."""

    file_path: str
    refactored_code: str
    unified_diff: str
    addresses_findings: int
    validated: bool
    validation_output: str
    notes: str = ""


class ReviewState(TypedDict, total=False):
    """State threaded through the graph.

    `agent_findings` and `patches` are reducer fields: parallel branches each
    return their own slice and LangGraph concatenates them. Everything else is
    written by exactly one node.
    """

    review_id: str
    llm_model: str

    #: Benchmark-only. When true, static_scan yields no findings so the LLM
    #: reviews without static evidence and aggregate has nothing to corroborate
    #: with - i.e. the pure "LLM-only" configuration measured in the benchmark.
    #: Absent (the default) keeps the production hybrid cross-validation.
    disable_static: bool

    files: list[SourceFile]
    static_findings: list[Finding]
    static_tools_run: list[str]
    static_tools_skipped: list[str]

    #: file path -> line numbers containing prompt-injection bait.
    injection_flags: dict[str, list[int]]

    agent_findings: Annotated[list[Finding], operator.add]
    patches: Annotated[list[PatchResult], operator.add]

    #: Post-aggregation, deduplicated and cross-validated.
    findings: list[Finding]
    suppressed_low_confidence: int

    risk_score: int
    error: str


class AgentTask(TypedDict):
    """Payload for one (layer, lens) branch."""

    review_id: str
    llm_model: str
    layer: Layer
    lens: Lens
    files: list[SourceFile]
    static_findings: list[Finding]
    injection_flags: dict[str, list[int]]


class RefactorTask(TypedDict):
    """Payload for refactoring one file."""

    review_id: str
    llm_model: str
    file: SourceFile
    findings: list[Finding]
