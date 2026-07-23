"""Secret scanner: provider patterns, entropy heuristic and placeholder skips."""

import pytest

from app.schemas.finding import Severity
from app.schemas.source import Language, SourceFile
from app.static_analysis.secrets import ENTROPY_THRESHOLD, scan_file, shannon_entropy


def make_file(content: str, path: str = "app.py") -> SourceFile:
    return SourceFile(path=path, content=content, language=Language.PYTHON)


@pytest.mark.parametrize(
    ("line", "expected_rule"),
    [
        ('AWS_KEY = "AKIAEXAMPLEFIXTURE00"', "SEC001"),
        ('TOKEN = "ghp_EXAMPLEFIXTURENOTAREALTOKEN0000000000"', "SEC003"),
        ('STRIPE = "sk_live_EXAMPLEFIXTURENOTAREALKEY000000"', "SEC005"),
        ('GOOGLE = "AIzaSyEXAMPLEFIXTURENOTAREALKEY00000000"', "SEC008"),
        ('SLACK = "xoxb-EXAMPLE-FIXTURE-NOT-A-REAL-TOKEN"', "SEC007"),
        ('DB = "postgresql://admin:EXAMPLE-FIXTURE-PW@db.internal:5432/app"', "SEC013"),
        ("KEY = '-----BEGIN RSA PRIVATE KEY-----'", "SEC009"),
    ],
)
def test_provider_patterns_are_detected(line: str, expected_rule: str) -> None:
    findings = scan_file(make_file(line))

    assert expected_rule in {f.rule_id for f in findings}


def test_provider_finding_is_high_severity_and_tagged() -> None:
    (finding,) = [
        f
        for f in scan_file(make_file('AWS_KEY = "AKIAEXAMPLEFIXTURE00"'))
        if f.rule_id == "SEC001"
    ]

    assert finding.severity is Severity.CRITICAL
    assert finding.category == "hardcoded-secret"
    assert finding.cwe == "CWE-798"
    assert finding.line_start == 1


def test_secret_value_is_redacted_in_the_explanation() -> None:
    secret = "ghp_EXAMPLEFIXTURENOTAREALTOKEN0000000000"

    findings = scan_file(make_file(f'TOKEN = "{secret}"'))

    assert findings
    assert all(secret not in f.explanation for f in findings)


def test_high_entropy_assignment_is_detected() -> None:
    findings = scan_file(make_file('API_KEY = "xQ9v2LmZ7pR4tW8nK3jH6yB1sD5gF0aC"'))

    assert "SEC100" in {f.rule_id for f in findings}


@pytest.mark.parametrize(
    "line",
    [
        'API_KEY = os.environ.get("API_KEY", "")',
        'API_KEY = "your-api-key-here"',
        'API_KEY = "change-me-in-your-local-env"',
        'API_KEY = "<INSERT_KEY>"',
        'password = "${DB_PASSWORD}"',
        "API_KEY = process.env.API_KEY",
    ],
)
def test_configuration_references_and_placeholders_are_ignored(line: str) -> None:
    assert scan_file(make_file(line)) == []


def test_non_credential_names_are_ignored_even_at_high_entropy() -> None:
    # A commit hash is high entropy but is not a credential.
    findings = scan_file(
        make_file('COMMIT_SHA = "9f8e7d6c5b4a39281706f5e4d3c2b1a09876f5e4"')
    )

    assert findings == []


def test_entropy_separates_random_strings_from_english() -> None:
    assert shannon_entropy("xQ9v2LmZ7pR4tW8nK3jH6yB1sD5gF0aC") > ENTROPY_THRESHOLD
    assert shannon_entropy("aaaaaaaaaaaaaaaaaaaaaaaa") < ENTROPY_THRESHOLD
    assert shannon_entropy("") == 0.0


def test_each_line_reports_a_rule_at_most_once() -> None:
    content = "\n".join(['A = "AKIAEXAMPLEFIXTURE00"'] * 3)

    findings = scan_file(make_file(content))

    assert len({f.line_start for f in findings}) == 3
