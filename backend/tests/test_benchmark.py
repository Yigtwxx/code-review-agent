"""Benchmark metric and label tests - no model, no database.

The benchmark package lives at the repo root, so it is put on the path here
before import. These tests pin the scoring rules (category + line tolerance),
the false-positive definition, and the ground-truth schema validation, so a
change to any of them fails loudly.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks import metrics  # noqa: E402
from benchmarks.report_writer import (  # noqa: E402
    render_config_table,
    render_model_table,
    splice_into_report,
)
from benchmarks.schema import (  # noqa: E402
    BenchmarkReport,
    CaseResult,
    DetectionResult,
    GroundTruth,
    GroundTruthDefect,
)

from app.agents.state import PatchResult  # noqa: E402
from app.schemas.finding import Finding, Origin, Severity  # noqa: E402

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parents[2] / "samples" / "vulnerable" / "ground_truth.json"
)


def _finding(
    line_start: int,
    category: str,
    *,
    line_end: int | None = None,
    severity: Severity = Severity.HIGH,
    origin: Origin = Origin.LLM,
) -> Finding:
    return Finding(
        file_path="vulnerable_api.py",
        line_start=line_start,
        line_end=line_end or line_start,
        severity=severity,
        category=category,
        title="t",
        explanation="e",
        origin=origin,
    )


def _defect(
    line_start: int, category: str, line_end: int | None = None
) -> GroundTruthDefect:
    return GroundTruthDefect(
        category=category, line_start=line_start, line_end=line_end or line_start
    )


# --- matching ---


@pytest.mark.parametrize(
    "finding_line,expected",
    [(28, True), (25, True), (31, True), (24, False), (32, False)],
)
def test_matches_line_within_tolerance_is_hit(
    finding_line: int, expected: bool
) -> None:
    finding = _finding(finding_line, "sql-injection")
    defect = _defect(28, "sql-injection")
    result = metrics.matches(finding, defect, tolerance=3)
    assert result is expected, f"line {finding_line} vs 28 (±3): expected {expected}"


def test_matches_wrong_category_same_line_is_miss() -> None:
    finding = _finding(28, "code-injection")
    defect = _defect(28, "sql-injection")
    assert not metrics.matches(finding, defect), "category mismatch must not match"


def test_matches_overlapping_ranges_is_hit() -> None:
    finding = _finding(24, "n-plus-one-query", line_end=27)
    defect = _defect(51, "n-plus-one-query", line_end=54)
    assert not metrics.matches(finding, defect), "disjoint ranges must not match"
    near = _finding(50, "n-plus-one-query", line_end=52)
    assert metrics.matches(near, defect), "overlapping ranges must match"


# --- detection ---


def test_detection_counts_matched_and_records_missed() -> None:
    defects = [
        _defect(28, "sql-injection"),
        _defect(46, "code-injection"),
        _defect(60, "insecure-deserialization"),
    ]
    findings = [_finding(29, "sql-injection"), _finding(46, "code-injection")]
    result = metrics.detection(findings, defects, tolerance=3)
    assert result.matched == 2, f"expected 2 matched, got {result.matched}"
    assert result.total == 3, f"expected 3 total, got {result.total}"
    assert result.missed == ["insecure-deserialization@60"], result.missed


def test_detection_empty_defects_is_zero_rate() -> None:
    result = metrics.detection([_finding(1, "xss")], [], tolerance=3)
    assert result.total == 0 and result.rate == 0.0, "no defects -> zero rate"


# --- false positives ---


@pytest.mark.parametrize(
    "severity,counts",
    [
        (Severity.CRITICAL, 1),
        (Severity.HIGH, 1),
        (Severity.MEDIUM, 0),
        (Severity.LOW, 0),
        (Severity.INFO, 0),
    ],
)
def test_false_positives_counts_only_critical_and_high(
    severity: Severity, counts: int
) -> None:
    findings = [_finding(1, "xss", severity=severity)]
    result = metrics.false_positives(findings)
    assert result == counts, f"{severity} should count as {counts}"


# --- fix accuracy ---


def test_fix_accuracy_ratio_of_validated_patches() -> None:
    patches = [
        PatchResult(
            file_path="a.py",
            refactored_code="x",
            unified_diff="d",
            addresses_findings=1,
            validated=True,
            validation_output="ok",
        ),
        PatchResult(
            file_path="b.py",
            refactored_code="y",
            unified_diff="d",
            addresses_findings=1,
            validated=False,
            validation_output="regressed",
        ),
    ]
    validated, total = metrics.fix_accuracy(patches)
    assert (validated, total) == (1, 2), f"expected (1, 2), got ({validated}, {total})"


def test_fix_accuracy_no_patches_is_zero_total() -> None:
    validated, total = metrics.fix_accuracy([])
    assert (validated, total) == (0, 0), "no patches -> (0, 0)"


def test_origin_breakdown_counts_by_provenance() -> None:
    findings = [
        _finding(1, "xss", origin=Origin.HYBRID),
        _finding(2, "sql-injection", origin=Origin.HYBRID),
        _finding(3, "code-injection", origin=Origin.LLM),
        _finding(4, "hardcoded-secret", origin=Origin.STATIC),
    ]
    result = metrics.origin_breakdown(findings)
    assert result == {"hybrid": 2, "llm": 1, "static": 1}, result


# --- ground truth schema ---


def test_ground_truth_file_loads_with_valid_categories() -> None:
    truth = GroundTruth.load(GROUND_TRUTH_PATH)
    total = sum(len(sample.defects) for sample in truth.samples.values())
    assert total >= 20, f"expected a substantial label set, got {total}"
    assert set(truth.samples) == {
        "vulnerable_api.py",
        "backend/orders.service.ts",
        "frontend/ProfileCard.tsx",
    }, sorted(truth.samples)


def test_ground_truth_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        GroundTruthDefect(category="not-a-real-category", line_start=1, line_end=1)


def test_ground_truth_defects_for_filters_by_file() -> None:
    truth = GroundTruth.load(GROUND_TRUTH_PATH)
    defects = truth.defects_for({"vulnerable_api.py"})
    assert all(d.category for d in defects), "every defect has a category"
    assert len(defects) == len(truth.samples["vulnerable_api.py"].defects), (
        "defects_for returns exactly the file's defects"
    )


# --- report writer ---


def _sample_report() -> BenchmarkReport:
    model_case = CaseResult(
        model="qwen3.6:35b-a3b",
        mode="hybrid",
        group="python",
        files=["vulnerable_api.py"],
        detection=DetectionResult(matched=12, total=15, missed=[]),
        false_positives=0,
        fix_validated=3,
        fix_total=4,
        latency_ms=300000,
        latency_ms_per_file=300000,
    )
    config_case = CaseResult(
        model="qwen3.6:35b-a3b",
        mode="static",
        group="all",
        files=["vulnerable_api.py"],
        detection=DetectionResult(matched=5, total=15, missed=[]),
        false_positives=0,
        latency_ms=2000,
    )
    return BenchmarkReport(model_cases=[model_case], config_cases=[config_case])


def test_render_model_table_includes_computed_cells() -> None:
    table = render_model_table(_sample_report().model_cases)
    assert "12/15 (80%)" in table, table
    assert "3/4 (75%)" in table, table
    assert "300 sn" in table, table


def test_render_config_table_labels_modes() -> None:
    table = render_config_table(_sample_report().config_cases)
    assert "Yalnızca statik analiz" in table, table
    assert "5/15" in table, table


def test_splice_into_report_replaces_empty_tables() -> None:
    model_header = (
        "| Model / Sistem | Test Edilen Dil | Bulunan Hata | Yanlış Alarm "
        "| Düzeltme Başarısı | İşlem Süresi |\n"
    )
    doc = (
        "> **Durum:** henüz tamamlanmadı.\n"
        "\n" + model_header + "|---|---|---|---|---|---|\n"
        "| `x` | Python | | | | |\n"
        "\n"
        "### ara\n"
        "\n"
        "| Yapılandırma | Detection Rate | False Positive | Süre |\n"
        "|---|---|---|---|\n"
        "| Hibrit | | | |\n"
        "\n"
        "son\n"
    )
    out = splice_into_report(doc, _sample_report())
    assert "12/15 (80%)" in out, "model table filled"
    assert "5/15" in out, "config table filled"
    assert "henüz tamamlanmadı" not in out, "status note replaced"
    assert "### ara" in out and "son" in out, "surrounding content preserved"
