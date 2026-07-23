"""Patch verification decides whether a suggested fix can be trusted.

Exercised without a model: `_validate` takes the original file and a candidate
replacement, so the real static tooling does the judging.
"""

from app.agents.nodes.refactor import _diff, _strip_fences, _validate
from app.schemas.finding import Finding, Layer, Lens, Origin, Severity
from app.schemas.source import Language, SourceFile

VULNERABLE = """import sqlite3


def get_user(username):
    conn = sqlite3.connect("app.db")
    query = "SELECT * FROM users WHERE name = '" + username + "'"
    return conn.execute(query).fetchall()
"""

FIXED = """import sqlite3


def get_user(username):
    conn = sqlite3.connect("app.db")
    return conn.execute(
        "SELECT * FROM users WHERE name = ?", (username,)
    ).fetchall()
"""


def source(content: str) -> SourceFile:
    return SourceFile(path="app.py", content=content, language=Language.PYTHON)


def finding(category: str = "sql-injection") -> Finding:
    return Finding(
        file_path="app.py",
        line_start=6,
        line_end=6,
        severity=Severity.CRITICAL,
        category=category,
        title="SQL injection",
        explanation="Kullanıcı girdisi sorguya birleştiriliyor.",
        origin=Origin.LLM,
        agent="BackendAgent",
        lens=Lens.SECURITY,
        layer=Layer.BACKEND,
        confidence=0.9,
    )


async def test_a_real_fix_is_validated() -> None:
    validated, report = await _validate(source(VULNERABLE), FIXED, [finding()])

    assert validated is True, report
    assert "giderildi" in report


async def test_a_fix_that_leaves_the_defect_is_rejected() -> None:
    """The model claiming a fix is not evidence of one."""
    unchanged_defect = VULNERABLE.replace("def get_user", "def fetch_user")

    validated, report = await _validate(
        source(VULNERABLE), unchanged_defect, [finding()]
    )

    assert validated is False
    assert "sql-injection" in report


async def test_a_fix_that_introduces_a_new_defect_is_rejected() -> None:
    worse = FIXED.replace(
        "import sqlite3", "import sqlite3\n\nAPI_KEY = 'sk_live_9aF3kQ2mZx7VbNp1'"
    )

    validated, report = await _validate(source(VULNERABLE), worse, [finding()])

    assert validated is False
    assert "yeni güvenlik bulgusu" in report


async def test_a_fix_that_breaks_the_syntax_is_rejected() -> None:
    broken = FIXED.replace("return conn.execute(", "return conn.execute(((")

    validated, report = await _validate(source(VULNERABLE), broken, [finding()])

    assert validated is False
    assert "ayrıştırılamıyor" in report.lower()


async def test_replacing_a_shell_call_with_an_argument_list_is_not_a_regression() -> (
    None
):
    """Bandit warns on every subprocess call; only the shell form is a defect."""
    before = (
        "import subprocess\n\n\n"
        "def ping(host):\n"
        '    return subprocess.check_output(f"ping -c 1 {host}", shell=True)\n'
    )
    after = (
        "import subprocess\n\n\n"
        "def ping(host):\n"
        '    return subprocess.check_output(["/sbin/ping", "-c", "1", host])\n'
    )

    validated, report = await _validate(
        source(before), after, [finding("command-injection")]
    )

    assert validated is True, report


async def test_findings_only_an_agent_raised_are_reported_as_unverifiable() -> None:
    """We do not claim to have verified what no tool can measure."""
    validated, report = await _validate(
        source(VULNERABLE), FIXED, [finding(), finding("broken-access-control")]
    )

    assert validated is True, report
    assert "doğrulanamadı" in report


def test_markdown_fences_are_stripped_from_model_output() -> None:
    assert _strip_fences("```python\nx = 1\n```") == "x = 1\n"
    assert _strip_fences("```\ny = 2\n```") == "y = 2\n"
    assert _strip_fences("z = 3") == "z = 3\n"


def test_diff_is_a_unified_diff_against_the_original() -> None:
    diff = _diff(source(VULNERABLE), FIXED)

    assert diff.startswith("--- a/app.py")
    assert "+++ b/app.py" in diff
    assert "-    query =" in diff
