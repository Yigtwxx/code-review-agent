"""The static layer must find the planted defects in the sample fixtures."""

from pathlib import Path

import pytest

from app.config import REPO_ROOT
from app.ingest.loader import load_directory, load_file
from app.schemas.finding import Origin, Severity
from app.static_analysis import ast_tool
from app.static_analysis.registry import run_all

VULNERABLE_DIR = REPO_ROOT / "samples" / "vulnerable"
CLEAN_DIR = REPO_ROOT / "samples" / "clean"


@pytest.fixture(scope="module")
def vulnerable_files():
    return load_directory(VULNERABLE_DIR)


async def test_pipeline_runs_every_applicable_tool(vulnerable_files) -> None:
    result = await run_all(vulnerable_files)

    assert set(result.tools_run) >= {"ruff", "bandit", "secret-scanner", "tree-sitter"}
    assert result.findings


async def test_python_injection_defects_are_found(vulnerable_files) -> None:
    result = await run_all(vulnerable_files)
    categories = {
        f.category for f in result.findings if f.file_path == "vulnerable_api.py"
    }

    assert "sql-injection" in categories
    assert "code-injection" in categories
    assert "command-injection" in categories
    assert "hardcoded-secret" in categories


async def test_typescript_defects_are_found(vulnerable_files) -> None:
    result = await run_all(vulnerable_files)
    ts_findings = [f for f in result.findings if f.file_path.endswith((".ts", ".tsx"))]

    if not ts_findings:
        pytest.skip("ESLint toolchain not installed (npm install in tools/eslint)")

    categories = {f.category for f in ts_findings}
    assert "code-injection" in categories or "command-injection" in categories


async def test_every_finding_is_marked_as_static_evidence(vulnerable_files) -> None:
    result = await run_all(vulnerable_files)

    assert all(f.origin is Origin.STATIC for f in result.findings)
    assert all(f.tool for f in result.findings)
    assert all(f.confidence >= 0.7 for f in result.findings)


async def test_findings_point_at_real_lines(vulnerable_files) -> None:
    by_path = {f.path: f.line_count for f in vulnerable_files}
    result = await run_all(vulnerable_files)

    for finding in result.findings:
        assert 1 <= finding.line_start <= by_path[finding.file_path]
        assert finding.line_end >= finding.line_start


async def test_clean_sample_produces_no_high_severity_findings() -> None:
    files = load_directory(CLEAN_DIR)
    assert files, "clean fixtures are missing"

    result = await run_all(files)
    serious = [
        f for f in result.findings if f.severity in {Severity.CRITICAL, Severity.HIGH}
    ]

    assert serious == [], f"false positives on clean code: {serious}"


async def test_empty_input_is_handled() -> None:
    result = await run_all([])

    assert result.findings == []


def test_tree_sitter_extracts_functions_and_classes() -> None:
    source = load_file(VULNERABLE_DIR / "vulnerable_api.py", base=VULNERABLE_DIR)
    assert source is not None

    structure = ast_tool.parse_structure(source)
    names = {unit.name for unit in structure.units}

    assert {"get_user", "search", "calculate", "hash_password"} <= names
    assert all(unit.line_end >= unit.line_start for unit in structure.units)


def test_tree_sitter_flags_a_long_and_deeply_nested_function(tmp_path: Path) -> None:
    body = "\n".join(
        [
            "def sprawling(a, b, c, d, e, f, g, h):",
            "    for i in a:",
            "        if b:",
            "            while c:",
            "                try:",
            "                    if d:",
            "                        pass",
            "                except Exception:",
            "                    pass",
            *["    x = 1" for _ in range(70)],
        ]
    )
    path = tmp_path / "big.py"
    path.write_text(body)
    source = load_file(path, base=tmp_path)
    assert source is not None

    categories = {f.category for f in ast_tool.analyse_file(source)}

    assert "long-function" in categories
    assert "deep-nesting" in categories
    assert "long-parameter-list" in categories
