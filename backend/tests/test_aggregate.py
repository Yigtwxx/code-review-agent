"""Cross-validation: how static evidence and agent findings are combined."""

from app.agents.nodes.aggregate import _merge
from app.schemas.finding import Finding, Layer, Lens, Origin, Severity


def static(
    line: int, category: str, *, tool="bandit", rule="B608", severity=Severity.HIGH
):
    return Finding(
        file_path="app.py",
        line_start=line,
        line_end=line,
        severity=severity,
        category=category,
        title=f"{rule}",
        explanation="static",
        origin=Origin.STATIC,
        tool=tool,
        rule_id=rule,
        confidence=0.95,
    )


def llm(
    line_start: int,
    category: str,
    *,
    line_end: int | None = None,
    confidence=0.6,
    severity=Severity.HIGH,
):
    return Finding(
        file_path="app.py",
        line_start=line_start,
        line_end=line_end or line_start,
        severity=severity,
        category=category,
        title="agent finding",
        explanation="detailed prose",
        suggested_fix="fixed()",
        origin=Origin.LLM,
        agent="BackendAgent",
        lens=Lens.SECURITY,
        layer=Layer.BACKEND,
        confidence=confidence,
    )


def test_agent_finding_confirmed_by_a_tool_becomes_hybrid() -> None:
    (merged,) = _merge([static(31, "sql-injection"), llm(31, "sql-injection")])

    assert merged.origin is Origin.HYBRID
    assert merged.corroborated_by == ["bandit:B608"]
    assert merged.corroborated_by_static is True


def test_corroboration_raises_confidence_but_never_past_one() -> None:
    (merged,) = _merge(
        [static(31, "sql-injection"), llm(31, "sql-injection", confidence=0.6)]
    )
    assert merged.confidence == 0.85

    (capped,) = _merge(
        [static(31, "sql-injection"), llm(31, "sql-injection", confidence=0.95)]
    )
    assert capped.confidence <= 1.0


def test_merged_finding_keeps_the_agents_prose_and_the_tools_rule() -> None:
    (merged,) = _merge([static(31, "sql-injection"), llm(31, "sql-injection")])

    assert merged.explanation == "detailed prose"
    assert merged.suggested_fix == "fixed()"
    assert merged.rule_id == "B608"


def test_two_tools_reporting_the_same_defect_collapse_to_one() -> None:
    merged = _merge(
        [
            static(31, "sql-injection", tool="bandit", rule="B608"),
            static(31, "sql-injection", tool="ruff", rule="S608"),
        ]
    )

    assert len(merged) == 1


def test_function_anchored_and_line_anchored_reports_merge() -> None:
    """A tool points at the statement; an agent reports the whole function."""
    merged = _merge(
        [static(31, "sql-injection"), llm(24, "sql-injection", line_end=33)]
    )

    assert len(merged) == 1
    assert merged[0].origin is Origin.HYBRID


def test_distant_findings_of_the_same_category_stay_separate() -> None:
    merged = _merge([static(10, "sql-injection"), static(90, "sql-injection")])

    assert len(merged) == 2


def test_different_categories_on_the_same_line_stay_separate() -> None:
    merged = _merge([static(10, "sql-injection"), llm(10, "xss")])

    assert len(merged) == 2


def test_merged_severity_is_the_highest_in_the_cluster() -> None:
    (merged,) = _merge(
        [
            static(31, "sql-injection", severity=Severity.MEDIUM),
            llm(31, "sql-injection", severity=Severity.CRITICAL),
        ]
    )

    assert merged.severity is Severity.CRITICAL


def test_uncorroborated_agent_finding_keeps_its_own_confidence() -> None:
    (merged,) = _merge([llm(31, "xss", confidence=0.6)])

    assert merged.origin is Origin.LLM
    assert merged.confidence == 0.6
    assert merged.corroborated_by == []


def test_security_lens_wins_attribution_over_quality_lens() -> None:
    """A quality lens spotting an RCE should not be credited with the finding."""
    quality = llm(43, "code-injection", confidence=0.99)
    quality.agent = "DatabaseAgent"
    quality.lens = Lens.QUALITY
    security = llm(43, "code-injection", confidence=0.99)
    security.agent = "BackendAgent"
    security.lens = Lens.SECURITY

    (merged,) = _merge([quality, security])

    assert merged.agent == "BackendAgent"
    assert merged.lens is Lens.SECURITY


def test_quality_lens_keeps_attribution_for_a_quality_finding() -> None:
    security = llm(26, "resource-leak", confidence=0.9)
    security.agent = "DatabaseAgent"
    security.lens = Lens.SECURITY
    quality = llm(26, "resource-leak", confidence=0.9)
    quality.agent = "BackendAgent"
    quality.lens = Lens.QUALITY

    (merged,) = _merge([security, quality])

    assert merged.lens is Lens.QUALITY


def test_higher_confidence_still_wins_within_the_same_lens() -> None:
    weak = llm(43, "code-injection", confidence=0.6)
    weak.lens = Lens.SECURITY
    strong = llm(43, "code-injection", confidence=0.95)
    strong.lens = Lens.SECURITY
    strong.title = "stronger"

    (merged,) = _merge([weak, strong])

    assert merged.title == "stronger"
