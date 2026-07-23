"""Domain vocabulary shared by static analysers, LLM agents and the API layer.

Everything that can produce a review comment - a linter, a secret scanner or a
layer agent - normalises its output into `Finding`. Keeping one shape is what
makes hybrid cross-validation (static evidence backing an LLM claim) possible.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


#: Contribution of a single finding to a review's risk score.
SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 10,
    Severity.MEDIUM: 4,
    Severity.LOW: 1,
    Severity.INFO: 0,
}

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Layer(StrEnum):
    """Architectural slice a file belongs to; decides which agent reviews it."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    CONFIG_INFRA = "config_infra"
    GENERIC = "generic"


class Lens(StrEnum):
    """Review perspective applied within a layer agent."""

    SECURITY = "security"
    QUALITY = "quality"


class Origin(StrEnum):
    """Where a finding came from - the basis of hallucination filtering."""

    STATIC = "static"
    LLM = "llm"
    #: An LLM finding that a deterministic tool independently confirmed.
    HYBRID = "hybrid"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Category(StrEnum):
    """Closed vocabulary shared by static tools and agents.

    Constraining the model to these exact slugs is what makes cross-validation
    work: an agent's `sql-injection` can be matched against Bandit's B608,
    which the catalog also maps to `sql-injection`. Free-text categories would
    make that comparison guesswork.
    """

    # --- security ---
    HARDCODED_SECRET = "hardcoded-secret"
    SQL_INJECTION = "sql-injection"
    COMMAND_INJECTION = "command-injection"
    CODE_INJECTION = "code-injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path-traversal"
    SSRF = "ssrf"
    CSRF = "csrf"
    OPEN_REDIRECT = "open-redirect"
    INSECURE_DESERIALIZATION = "insecure-deserialization"
    XML_PARSING_VULNERABLE = "xml-parsing-vulnerable"
    BROKEN_ACCESS_CONTROL = "broken-access-control"
    MISSING_AUTHENTICATION = "missing-authentication"
    MASS_ASSIGNMENT = "mass-assignment"
    WEAK_HASH = "weak-hash"
    WEAK_CIPHER = "weak-cipher"
    WEAK_RANDOMNESS = "weak-randomness"
    TLS_VERIFICATION_DISABLED = "tls-verification-disabled"
    DEBUG_MODE_ENABLED = "debug-mode-enabled"
    BIND_ALL_INTERFACES = "bind-all-interfaces"
    PERMISSIVE_CORS = "permissive-cors"
    SENSITIVE_DATA_LOGGED = "sensitive-data-logged"
    SENSITIVE_DATA_UNENCRYPTED = "sensitive-data-unencrypted"
    RATE_LIMIT_MISSING = "rate-limit-missing"
    PROTOTYPE_POLLUTION = "prototype-pollution"
    TIMING_ATTACK = "timing-attack"
    REDOS = "redos"
    INSECURE_TEMP_FILE = "insecure-temp-file"
    CONTAINER_RUNS_AS_ROOT = "container-runs-as-root"
    UNPINNED_DEPENDENCY = "unpinned-dependency"

    # --- correctness & quality ---
    UNDEFINED_NAME = "undefined-name"
    RACE_CONDITION = "race-condition"
    RESOURCE_LEAK = "resource-leak"
    SWALLOWED_EXCEPTION = "swallowed-exception"
    BARE_EXCEPT = "bare-except"
    ERROR_HANDLING = "error-handling"
    N_PLUS_ONE_QUERY = "n-plus-one-query"
    MISSING_INDEX = "missing-index"
    IRREVERSIBLE_MIGRATION = "irreversible-migration"
    LONG_FUNCTION = "long-function"
    DEEP_NESTING = "deep-nesting"
    LONG_PARAMETER_LIST = "long-parameter-list"
    DUPLICATED_LOGIC = "duplicated-logic"
    DEAD_CODE = "dead-code"
    UNUSED_VARIABLE = "unused-variable"
    UNUSED_IMPORT = "unused-import"
    NAMING_CONVENTION = "naming-convention"
    LAYER_VIOLATION = "layer-violation"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    UNNECESSARY_RERENDER = "unnecessary-rerender"
    CODE_QUALITY = "code-quality"


#: Categories that count as security issues when scoring and reporting.
SECURITY_CATEGORIES: frozenset[str] = frozenset(
    {
        Category.HARDCODED_SECRET,
        Category.SQL_INJECTION,
        Category.COMMAND_INJECTION,
        Category.CODE_INJECTION,
        Category.XSS,
        Category.PATH_TRAVERSAL,
        Category.SSRF,
        Category.CSRF,
        Category.OPEN_REDIRECT,
        Category.INSECURE_DESERIALIZATION,
        Category.XML_PARSING_VULNERABLE,
        Category.BROKEN_ACCESS_CONTROL,
        Category.MISSING_AUTHENTICATION,
        Category.MASS_ASSIGNMENT,
        Category.WEAK_HASH,
        Category.WEAK_CIPHER,
        Category.WEAK_RANDOMNESS,
        Category.TLS_VERIFICATION_DISABLED,
        Category.DEBUG_MODE_ENABLED,
        Category.BIND_ALL_INTERFACES,
        Category.PERMISSIVE_CORS,
        Category.SENSITIVE_DATA_LOGGED,
        Category.SENSITIVE_DATA_UNENCRYPTED,
        Category.RATE_LIMIT_MISSING,
        Category.PROTOTYPE_POLLUTION,
        Category.TIMING_ATTACK,
        Category.REDOS,
        Category.INSECURE_TEMP_FILE,
        Category.CONTAINER_RUNS_AS_ROOT,
    }
)


class Finding(BaseModel):
    """A single review comment anchored to a line range in a file."""

    file_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    severity: Severity
    #: Stable machine slug, e.g. "sql-injection", "hardcoded-secret".
    category: str
    title: str
    explanation: str
    suggested_fix: str | None = None

    owasp: str | None = None
    cwe: str | None = None

    origin: Origin
    #: Tool that produced it when origin is STATIC, e.g. "bandit".
    tool: str | None = None
    #: Tool rule id, e.g. "B608", "S105".
    rule_id: str | None = None
    #: Agent that produced it when origin is LLM/HYBRID, e.g. "BackendAgent".
    agent: str | None = None
    lens: Lens | None = None
    layer: Layer | None = None

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Static rule ids that independently support this finding.
    corroborated_by: list[str] = Field(default_factory=list)

    @property
    def corroborated_by_static(self) -> bool:
        return bool(self.corroborated_by)


class LlmFinding(BaseModel):
    """Reduced schema the model is constrained to emit.

    Provenance fields (`origin`, `agent`, `lens`, ...) are filled in by us, not
    by the model - it cannot claim static-tool corroboration it did not earn.
    """

    line_start: int = Field(ge=1, description="First line of the offending code")
    line_end: int = Field(ge=1, description="Last line of the offending code")
    severity: Severity
    category: Category = Field(description="Closest matching category")
    title: str = Field(description="One-line summary of the problem, in Turkish")
    explanation: str = Field(
        description="Why this is a problem and what an attacker gains, in Turkish"
    )
    suggested_fix: str | None = Field(
        default=None, description="Corrected code for these lines only, no prose"
    )
    cwe: str | None = Field(default=None, description="e.g. CWE-89")
    confidence: float = Field(
        ge=0.0, le=1.0, description="0..1 certainty that this is a real defect"
    )


class LlmFindingList(BaseModel):
    """Top-level object the model returns; a bare array is harder to constrain."""

    findings: list[LlmFinding] = Field(default_factory=list)
