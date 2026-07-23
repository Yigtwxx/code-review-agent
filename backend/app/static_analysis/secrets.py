"""Secret leak detection.

Two complementary strategies:

* **Provider patterns** - vendor key formats (AWS, GitHub, Stripe, ...) are
  distinctive enough to report on sight, with essentially no false positives.
* **Assignment + entropy** - a variable whose *name* suggests a credential and
  whose *value* is high-entropy. Entropy alone flags UUIDs and hashes, and the
  name alone flags `api_key = os.environ[...]`, so both must agree.

Runs in-process: no file needs to leave the workspace and no secret is logged.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.schemas.finding import Finding, Origin, Severity
from app.schemas.source import SourceFile

TOOL_NAME = "secret-scanner"

_OWASP_AUTH = "A07:2021-Identification and Authentication Failures"
_CWE_HARDCODED = "CWE-798"


@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    name: str
    pattern: re.Pattern[str]
    severity: Severity
    #: When set, the captured value must exceed this Shannon entropy.
    min_entropy: float | None = None


PROVIDER_RULES: tuple[SecretRule, ...] = (
    SecretRule(
        "SEC001",
        "AWS access key id",
        re.compile(r"\b((?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC002",
        "AWS secret access key",
        re.compile(
            r"(?i)aws.{0,20}?(?:secret|private).{0,20}?['\"]([0-9a-zA-Z/+]{40})['\"]"
        ),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC003",
        "GitHub token",
        re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,255})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC004",
        "GitHub fine-grained token",
        re.compile(r"\b(github_pat_[0-9A-Za-z_]{22,255})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC005",
        "Stripe live secret key",
        re.compile(r"\b((?:sk|rk)_live_[0-9A-Za-z]{10,99})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC006",
        "Stripe test key",
        re.compile(r"\b((?:sk|rk)_test_[0-9A-Za-z]{10,99})\b"),
        Severity.MEDIUM,
    ),
    SecretRule(
        "SEC007",
        "Slack token",
        re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC008",
        "Google API key",
        re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b"),
        Severity.HIGH,
    ),
    SecretRule(
        "SEC009",
        "Private key block",
        re.compile(r"(-----BEGIN(?: [A-Z]+)? PRIVATE KEY(?: BLOCK)?-----)"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC010",
        "OpenAI API key",
        re.compile(r"\b(sk-(?:proj-)?[0-9A-Za-z_-]{20,})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC011",
        "Anthropic API key",
        re.compile(r"\b(sk-ant-[0-9A-Za-z_-]{20,})\b"),
        Severity.CRITICAL,
    ),
    SecretRule(
        "SEC012",
        "JSON Web Token",
        re.compile(r"\b(eyJ[0-9A-Za-z_-]{10,}\.eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]+)"),
        Severity.MEDIUM,
    ),
    SecretRule(
        "SEC013",
        "Credentials embedded in a connection URI",
        re.compile(
            r"\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqp|https?)"
            r"://[^\s:@/]+:([^\s:@/]{4,})@"
        ),
        Severity.HIGH,
    ),
)

#: Names that mark a value as a credential.
_SECRET_NAME = re.compile(
    r"(?i)\b\w*("
    r"api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|private[_-]?key|passwd|password|passphrase|"
    r"secret|token|credential"
    r")\w*\b"
)

#: `NAME = "value"` / `NAME: "value"` in Python, JS/TS, YAML and .env files.
_ASSIGNMENT = re.compile(
    r"""(?P<name>[A-Za-z_][A-Za-z0-9_.\[\]'"-]*)\s*[:=]\s*"""
    r"""(?P<quote>['"])(?P<value>[^'"\n]{8,})(?P=quote)"""
)

#: Values that look like secrets but are obviously not real ones.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "your-",
    "your_",
    "yourkey",
    "example",
    "placeholder",
    "dummy",
    "sample",
    "insert",
    "todo",
    "fixme",
    "xxxx",
    "<",
    "{{",
    "${",
    "%s",
    "test-key",
    "fake",
    "redacted",
    "n/a",
    "none",
    "null",
)

#: A value that is really a reference to configuration, not a literal secret.
_REFERENCE = re.compile(
    r"(?i)(os\.environ|getenv|process\.env|settings\.|config\.|vault|secretsmanager)"
)

#: Below this, a string is too structured to be a random credential.
ENTROPY_THRESHOLD = 3.6


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character."""
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def _is_obviously_fake(value: str) -> bool:
    """Only filler nobody could mistake for a key, e.g. "aaaaaaaaaaaa"."""
    return len(set(value.lower())) <= 2


def _is_placeholder(value: str) -> bool:
    """Filler *or* documentation-style stand-ins like `your-api-key-here`.

    Applied to the entropy heuristic only. Provider formats (`AKIA…`, `ghp_…`)
    are specific enough to report on sight - and a key that ships with
    "EXAMPLE" in it is still a key that should not be in the source tree.
    """
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return True
    return _is_obviously_fake(value)


def scan_file(file: SourceFile) -> list[Finding]:
    """Report credentials hardcoded in a single file."""
    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()

    for line_number, line in enumerate(file.content.splitlines(), start=1):
        if len(line) > 2000:
            # Minified or generated line; entropy is meaningless here.
            continue

        for rule in PROVIDER_RULES:
            match = rule.pattern.search(line)
            if match is None:
                continue
            value = match.group(1) if match.groups() else match.group(0)
            if _is_obviously_fake(value):
                continue
            key = (line_number, rule.rule_id)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                _finding(
                    file,
                    line_number,
                    rule.rule_id,
                    rule.severity,
                    title=f"Hardcoded {rule.name}",
                    explanation=(
                        f"Bu satırda {rule.name} formatına uyan bir kimlik bilgisi "
                        f"gömülü görünüyor ({_redact(value)}). Sürüm kontrolüne giren "
                        "her secret sızmış kabul edilmeli: anahtarı iptal edin ve "
                        "değeri ortam değişkeninden okuyun."
                    ),
                )
            )

        finding = _scan_assignment(file, line_number, line)
        if finding is not None and (line_number, "SEC100") not in seen:
            seen.add((line_number, "SEC100"))
            findings.append(finding)

    return findings


def _scan_assignment(file: SourceFile, line_number: int, line: str) -> Finding | None:
    match = _ASSIGNMENT.search(line)
    if match is None:
        return None

    name = match.group("name")
    value = match.group("value")
    if not _SECRET_NAME.search(name):
        return None
    if _REFERENCE.search(line) or _is_placeholder(value):
        return None
    if shannon_entropy(value) < ENTROPY_THRESHOLD:
        return None

    return _finding(
        file,
        line_number,
        "SEC100",
        Severity.HIGH,
        title="Hardcoded credential in assignment",
        explanation=(
            f"`{name}` değişkenine yüksek entropili ({shannon_entropy(value):.2f} bit/"
            f"karakter) sabit bir değer atanmış ({_redact(value)}). Kimlik bilgisi "
            "gibi görünüyor; ortam değişkenine taşıyın ve mevcut değeri iptal edin."
        ),
    )


def _finding(
    file: SourceFile,
    line_number: int,
    rule_id: str,
    severity: Severity,
    *,
    title: str,
    explanation: str,
) -> Finding:
    return Finding(
        file_path=file.path,
        line_start=line_number,
        line_end=line_number,
        severity=severity,
        category="hardcoded-secret",
        title=title,
        explanation=explanation,
        suggested_fix=None,
        owasp=_OWASP_AUTH,
        cwe=_CWE_HARDCODED,
        origin=Origin.STATIC,
        tool=TOOL_NAME,
        rule_id=rule_id,
        confidence=0.95,
    )


def _redact(value: str) -> str:
    """Show just enough to locate the value without reprinting the secret."""
    if len(value) <= 8:
        return f"{value[:2]}***"
    return f"{value[:4]}***{value[-2:]}"


def analyse(files: list[SourceFile]) -> list[Finding]:
    findings: list[Finding] = []
    for file in files:
        findings.extend(scan_file(file))
    return findings
