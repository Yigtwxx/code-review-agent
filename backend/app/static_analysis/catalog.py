"""Rule metadata: tool rule id -> severity, category, OWASP and CWE.

Linters speak in rule codes; the review UI speaks in security categories. This
table is the translation layer, and it is also what lets an LLM finding be
matched against deterministic evidence: both sides end up carrying the same
`category` slug.
"""

from typing import NamedTuple

from app.schemas.finding import Severity


class RuleInfo(NamedTuple):
    category: str
    severity: Severity
    owasp: str | None = None
    cwe: str | None = None


_INJECTION = "A03:2021-Injection"
_CRYPTO_FAILURE = "A02:2021-Cryptographic Failures"
_MISCONFIG = "A05:2021-Security Misconfiguration"
_AUTH_FAILURE = "A07:2021-Identification and Authentication Failures"
_INTEGRITY = "A08:2021-Software and Data Integrity Failures"
_SSRF = "A10:2021-Server-Side Request Forgery"

#: Bandit codes and their ruff/flake8-bandit twins (B105 == S105) share meaning,
#: so each entry is registered under both prefixes below.
_SHARED_SECURITY_RULES: dict[str, RuleInfo] = {
    "101": RuleInfo("assert-used", Severity.LOW, None, "CWE-703"),
    "104": RuleInfo("bind-all-interfaces", Severity.MEDIUM, _MISCONFIG, "CWE-605"),
    "105": RuleInfo("hardcoded-secret", Severity.HIGH, _AUTH_FAILURE, "CWE-798"),
    "106": RuleInfo("hardcoded-secret", Severity.HIGH, _AUTH_FAILURE, "CWE-798"),
    "107": RuleInfo("hardcoded-secret", Severity.HIGH, _AUTH_FAILURE, "CWE-798"),
    "108": RuleInfo("insecure-temp-file", Severity.LOW, _MISCONFIG, "CWE-377"),
    "110": RuleInfo("swallowed-exception", Severity.LOW, None, "CWE-390"),
    "201": RuleInfo("debug-mode-enabled", Severity.HIGH, _MISCONFIG, "CWE-489"),
    "301": RuleInfo("insecure-deserialization", Severity.HIGH, _INTEGRITY, "CWE-502"),
    "302": RuleInfo("insecure-deserialization", Severity.HIGH, _INTEGRITY, "CWE-502"),
    "303": RuleInfo("weak-hash", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-327"),
    "304": RuleInfo("weak-cipher", Severity.HIGH, _CRYPTO_FAILURE, "CWE-327"),
    "305": RuleInfo("weak-cipher-mode", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-327"),
    "306": RuleInfo("insecure-temp-file", Severity.MEDIUM, _MISCONFIG, "CWE-377"),
    "307": RuleInfo("code-injection", Severity.CRITICAL, _INJECTION, "CWE-95"),
    "310": RuleInfo("ssrf", Severity.MEDIUM, _SSRF, "CWE-918"),
    "311": RuleInfo("weak-randomness", Severity.LOW, _CRYPTO_FAILURE, "CWE-330"),
    "312": RuleInfo("telnet-usage", Severity.HIGH, _CRYPTO_FAILURE, "CWE-319"),
    "313": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "314": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "315": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "316": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "317": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "318": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "319": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "321": RuleInfo("ftp-usage", Severity.HIGH, _CRYPTO_FAILURE, "CWE-319"),
    "324": RuleInfo("weak-hash", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-327"),
    "401": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "403": RuleInfo("insecure-deserialization", Severity.MEDIUM, _INTEGRITY, "CWE-502"),
    "404": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "405": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "411": RuleInfo("xml-parsing-vulnerable", Severity.MEDIUM, _INJECTION, "CWE-611"),
    "413": RuleInfo("weak-cipher", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-327"),
    "501": RuleInfo(
        "tls-verification-disabled", Severity.HIGH, _CRYPTO_FAILURE, "CWE-295"
    ),
    "502": RuleInfo("insecure-ssl-version", Severity.HIGH, _CRYPTO_FAILURE, "CWE-327"),
    "503": RuleInfo("insecure-ssl-version", Severity.HIGH, _CRYPTO_FAILURE, "CWE-327"),
    "506": RuleInfo("insecure-deserialization", Severity.HIGH, _INTEGRITY, "CWE-502"),
    "507": RuleInfo(
        "host-key-verification-disabled", Severity.HIGH, _CRYPTO_FAILURE, "CWE-295"
    ),
    "601": RuleInfo("command-injection", Severity.HIGH, _INJECTION, "CWE-78"),
    "602": RuleInfo("command-injection", Severity.CRITICAL, _INJECTION, "CWE-78"),
    # B603/B604/B606/B607 fire on *any* subprocess call, including the safe
    # argument-list form. Rating them MEDIUM would mark a file that correctly
    # replaced `shell=True` with `execFile`-style arguments as a regression.
    "603": RuleInfo("command-injection", Severity.LOW, _INJECTION, "CWE-78"),
    "604": RuleInfo("command-injection", Severity.LOW, _INJECTION, "CWE-78"),
    "605": RuleInfo("command-injection", Severity.HIGH, _INJECTION, "CWE-78"),
    "606": RuleInfo("command-injection", Severity.LOW, _INJECTION, "CWE-78"),
    "607": RuleInfo("command-injection", Severity.LOW, _INJECTION, "CWE-78"),
    "608": RuleInfo("sql-injection", Severity.HIGH, _INJECTION, "CWE-89"),
    "609": RuleInfo("command-injection", Severity.HIGH, _INJECTION, "CWE-78"),
    "610": RuleInfo("sql-injection", Severity.HIGH, _INJECTION, "CWE-89"),
    "611": RuleInfo("sql-injection", Severity.HIGH, _INJECTION, "CWE-89"),
    "612": RuleInfo("logging-misconfiguration", Severity.LOW, _MISCONFIG, "CWE-532"),
    "701": RuleInfo("xss", Severity.HIGH, _INJECTION, "CWE-79"),
    "702": RuleInfo("xss", Severity.MEDIUM, _INJECTION, "CWE-79"),
    "703": RuleInfo("xss", Severity.HIGH, _INJECTION, "CWE-79"),
}

#: Non-security ruff rules worth surfacing, keyed by full code.
_QUALITY_RULES: dict[str, RuleInfo] = {
    "F821": RuleInfo("undefined-name", Severity.HIGH, None, "CWE-457"),
    "F811": RuleInfo("redefinition", Severity.MEDIUM),
    "F841": RuleInfo("unused-variable", Severity.LOW),
    "F401": RuleInfo("unused-import", Severity.LOW),
    "F632": RuleInfo("identity-comparison-misuse", Severity.MEDIUM),
    "E501": RuleInfo("line-too-long", Severity.INFO),
    "E722": RuleInfo("bare-except", Severity.MEDIUM, None, "CWE-396"),
    "E711": RuleInfo("none-comparison", Severity.LOW),
    "E712": RuleInfo("bool-comparison", Severity.LOW),
    "B006": RuleInfo("mutable-default-argument", Severity.MEDIUM),
    "B008": RuleInfo("function-call-in-default", Severity.LOW),
    "B904": RuleInfo("exception-chaining-missing", Severity.LOW),
    "C901": RuleInfo("high-complexity", Severity.MEDIUM),
    "N806": RuleInfo("naming-convention", Severity.INFO),
}

#: ESLint rule id -> metadata. Security rules come from eslint-plugin-security.
ESLINT_RULES: dict[str, RuleInfo] = {
    "no-eval": RuleInfo("code-injection", Severity.CRITICAL, _INJECTION, "CWE-95"),
    "no-implied-eval": RuleInfo("code-injection", Severity.HIGH, _INJECTION, "CWE-95"),
    "no-new-func": RuleInfo("code-injection", Severity.HIGH, _INJECTION, "CWE-95"),
    "no-script-url": RuleInfo("xss", Severity.MEDIUM, _INJECTION, "CWE-79"),
    "react/no-danger": RuleInfo("xss", Severity.HIGH, _INJECTION, "CWE-79"),
    "security/detect-eval-with-expression": RuleInfo(
        "code-injection", Severity.CRITICAL, _INJECTION, "CWE-95"
    ),
    "security/detect-non-literal-regexp": RuleInfo(
        "redos", Severity.MEDIUM, None, "CWE-1333"
    ),
    "security/detect-unsafe-regex": RuleInfo("redos", Severity.HIGH, None, "CWE-1333"),
    "security/detect-buffer-noassert": RuleInfo(
        "buffer-overflow", Severity.MEDIUM, None, "CWE-119"
    ),
    "security/detect-child-process": RuleInfo(
        "command-injection", Severity.HIGH, _INJECTION, "CWE-78"
    ),
    "security/detect-disable-mustache-escape": RuleInfo(
        "xss", Severity.HIGH, _INJECTION, "CWE-79"
    ),
    "security/detect-no-csrf-before-method-override": RuleInfo(
        "csrf", Severity.MEDIUM, _MISCONFIG, "CWE-352"
    ),
    "security/detect-non-literal-fs-filename": RuleInfo(
        "path-traversal", Severity.HIGH, _INJECTION, "CWE-22"
    ),
    "security/detect-non-literal-require": RuleInfo(
        "code-injection", Severity.MEDIUM, _INJECTION, "CWE-95"
    ),
    "security/detect-object-injection": RuleInfo(
        "prototype-pollution", Severity.LOW, _INJECTION, "CWE-1321"
    ),
    "security/detect-possible-timing-attacks": RuleInfo(
        "timing-attack", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-208"
    ),
    "security/detect-pseudoRandomBytes": RuleInfo(
        "weak-randomness", Severity.MEDIUM, _CRYPTO_FAILURE, "CWE-330"
    ),
    "security/detect-new-buffer": RuleInfo(
        "buffer-overflow", Severity.MEDIUM, None, "CWE-119"
    ),
    "no-unused-vars": RuleInfo("unused-variable", Severity.LOW),
    "no-undef": RuleInfo("undefined-name", Severity.HIGH, None, "CWE-457"),
    "eqeqeq": RuleInfo("loose-equality", Severity.LOW),
}

_DEFAULT_QUALITY = RuleInfo("code-quality", Severity.LOW)


def lookup_python_rule(code: str) -> RuleInfo:
    """Resolve a bandit (`B608`) or ruff (`S608`, `F821`) rule code."""
    if code in _QUALITY_RULES:
        return _QUALITY_RULES[code]
    if code[:1] in {"B", "S"} and code[1:] in _SHARED_SECURITY_RULES:
        return _SHARED_SECURITY_RULES[code[1:]]
    return _DEFAULT_QUALITY


def lookup_eslint_rule(rule_id: str) -> RuleInfo:
    if rule_id in ESLINT_RULES:
        return ESLINT_RULES[rule_id]
    if rule_id.startswith("security/"):
        return RuleInfo("insecure-pattern", Severity.MEDIUM, _MISCONFIG)
    return _DEFAULT_QUALITY
