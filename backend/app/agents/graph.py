"""The review graph.

    static_scan → partition → injection_guard ─┬─► FrontendAgent · security ─┐
                                               ├─► FrontendAgent · quality   │
                                               ├─► BackendAgent  · security  ├─► agg
                                               ├─► ...                       │
                                               └─► GenericAgent  · quality ──┘
                                                                              │
        report ◄── refactor_file ◄──┬── hallucination_check ◄─────────────────┘
                                    └── (one branch per affected file)

Two fan-outs, both driven by `Send`: one over (layer, lens) pairs, one over the
files that ended up with fixable findings. Nothing is hardcoded about how many
branches there are - a submission with only Python backend files runs two
agents, a full-stack one runs ten.
"""

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.nodes.aggregate import aggregate
from app.agents.nodes.hallucination import hallucination_check
from app.agents.nodes.injection_node import injection_guard
from app.agents.nodes.layer_agent import layer_agent
from app.agents.nodes.partition_node import partition_files
from app.agents.nodes.refactor import refactor_file
from app.agents.nodes.report import report
from app.agents.nodes.static_scan import static_scan
from app.agents.state import AgentTask, RefactorTask, ReviewState
from app.schemas.finding import SEVERITY_ORDER, Finding, Layer, Lens, Severity
from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

#: Only defects at least this severe are worth spending a refactor call on.
REFACTOR_MIN_SEVERITY = Severity.MEDIUM

#: Cap on files refactored per review, so one large submission cannot occupy
#: the local model indefinitely. Highest-risk files are chosen first.
MAX_REFACTORED_FILES = 10


def fan_out_agents(state: ReviewState) -> list[Send] | str:
    """One branch per (layer, lens) that actually has files."""
    # The partition node already annotated each file; regrouping here avoids
    # classifying twice and keeps the two steps from ever disagreeing.
    grouped: dict[Layer, list[SourceFile]] = {}
    for file in state["files"]:
        for name in file.layers or [Layer.GENERIC.value]:
            grouped.setdefault(Layer(name), []).append(file)

    static = state.get("static_findings", [])
    flags = state.get("injection_flags", {})

    sends: list[Send] = []
    for layer, files in grouped.items():
        paths = {file.path for file in files}
        relevant = [f for f in static if f.file_path in paths]
        for lens in (Lens.SECURITY, Lens.QUALITY):
            task: AgentTask = {
                "review_id": state["review_id"],
                "llm_model": state["llm_model"],
                "layer": layer,
                "lens": lens,
                "files": files,
                "static_findings": relevant,
                "injection_flags": flags,
            }
            sends.append(Send("layer_agent", task))

    if not sends:
        # Nothing to review by model; the static findings still stand.
        return "aggregate"
    logger.info("Dispatching %d agent branches", len(sends))
    return sends


def fan_out_refactor(state: ReviewState) -> list[Send] | str:
    """One branch per file worth refactoring, highest risk first."""
    findings = state.get("findings", [])
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        if SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[REFACTOR_MIN_SEVERITY]:
            continue
        by_file.setdefault(finding.file_path, []).append(finding)

    if not by_file:
        return "report"

    ranked = sorted(
        by_file.items(),
        key=lambda item: -sum(SEVERITY_ORDER[f.severity] for f in item[1]),
    )[:MAX_REFACTORED_FILES]

    files = {file.path: file for file in state["files"]}
    sends = [
        Send(
            "refactor_file",
            RefactorTask(
                review_id=state["review_id"],
                llm_model=state["llm_model"],
                file=files[path],
                findings=sorted(
                    file_findings, key=lambda f: -SEVERITY_ORDER[f.severity]
                ),
            ),
        )
        for path, file_findings in ranked
        if path in files
    ]
    if len(by_file) > len(sends):
        logger.info(
            "Refactoring %d of %d affected files (cap %d)",
            len(sends),
            len(by_file),
            MAX_REFACTORED_FILES,
        )
    return sends or "report"


def build_graph():
    """Compile the review graph."""
    builder = StateGraph(ReviewState)

    builder.add_node("static_scan", static_scan)
    builder.add_node("partition", partition_files)
    builder.add_node("injection_guard", injection_guard)
    builder.add_node("layer_agent", layer_agent)
    builder.add_node("aggregate", aggregate)
    builder.add_node("hallucination_check", hallucination_check)
    builder.add_node("refactor_file", refactor_file)
    builder.add_node("report", report)

    builder.add_edge(START, "static_scan")
    builder.add_edge("static_scan", "partition")
    builder.add_edge("partition", "injection_guard")

    builder.add_conditional_edges(
        "injection_guard", fan_out_agents, ["layer_agent", "aggregate"]
    )
    builder.add_edge("layer_agent", "aggregate")
    builder.add_edge("aggregate", "hallucination_check")

    builder.add_conditional_edges(
        "hallucination_check", fan_out_refactor, ["refactor_file", "report"]
    )
    builder.add_edge("refactor_file", "report")
    builder.add_edge("report", END)

    return builder.compile()


#: Compiled once; the graph is stateless between runs.
review_graph = build_graph()
