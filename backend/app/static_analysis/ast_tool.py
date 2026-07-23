"""Tree-sitter analysis.

Serves two purposes:

* **Structure** - splitting a file at function and class boundaries so agents
  receive semantically whole units instead of arbitrary character windows.
* **Metrics** - long functions, deep nesting and long parameter lists are
  measured rather than guessed at, so the quality lens starts from facts.

Tree-sitter is error-tolerant, so a syntactically broken file still yields a
partial tree instead of an exception.
"""

import logging
from dataclasses import dataclass, field

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.schemas.finding import Finding, Origin, Severity
from app.schemas.source import Language, SourceFile

logger = logging.getLogger(__name__)

TOOL_NAME = "tree-sitter"

#: Our language enum -> tree-sitter grammar name.
_GRAMMARS: dict[Language, str] = {
    Language.PYTHON: "python",
    Language.TYPESCRIPT: "typescript",
    Language.TSX: "tsx",
    Language.JAVASCRIPT: "javascript",
    Language.JSX: "javascript",
    Language.SQL: "sql",
    Language.YAML: "yaml",
    Language.JSON: "json",
    Language.DOCKERFILE: "dockerfile",
    Language.HTML: "html",
    Language.CSS: "css",
    Language.SHELL: "bash",
}

_FUNCTION_NODES = frozenset(
    {
        "function_definition",
        "function_declaration",
        "function_expression",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
    }
)

_CLASS_NODES = frozenset({"class_definition", "class_declaration"})

_NESTING_NODES = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_clause",
        "while_statement",
        "try_statement",
        "with_statement",
        "switch_statement",
        "catch_clause",
        "do_statement",
    }
)

#: Thresholds above which we raise a maintainability finding.
MAX_FUNCTION_LINES = 60
MAX_NESTING_DEPTH = 4
MAX_PARAMETERS = 6


@dataclass
class CodeUnit:
    """A function or class, used as an agent's review chunk."""

    name: str
    kind: str
    line_start: int
    line_end: int
    text: str

    @property
    def line_count(self) -> int:
        return self.line_end - self.line_start + 1


@dataclass
class FileStructure:
    units: list[CodeUnit] = field(default_factory=list)
    parse_error: bool = False


def _grammar_for(language: Language) -> str | None:
    return _GRAMMARS.get(language)


def parse_structure(file: SourceFile) -> FileStructure:
    """Extract top-level functions and classes from a file."""
    grammar = _grammar_for(file.language)
    if grammar is None:
        return FileStructure()

    try:
        parser = get_parser(grammar)
        tree = parser.parse(file.content.encode("utf-8"))
    except Exception as exc:  # grammar load or parse failure
        logger.info("tree-sitter could not parse %s: %s", file.path, exc)
        return FileStructure(parse_error=True)

    units: list[CodeUnit] = []
    _collect(tree.root_node, file.content.encode("utf-8"), units)
    return FileStructure(units=units, parse_error=tree.root_node.has_error)


def _collect(node: Node, source: bytes, out: list[CodeUnit]) -> None:
    """Walk the tree, recording function and class nodes."""
    if node.type in _FUNCTION_NODES or node.type in _CLASS_NODES:
        out.append(
            CodeUnit(
                name=_node_name(node, source),
                kind="class" if node.type in _CLASS_NODES else "function",
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                text=source[node.start_byte : node.end_byte].decode(
                    "utf-8", errors="replace"
                ),
            )
        )
        # Methods inside a class are still worth recording individually.
        if node.type in _CLASS_NODES:
            for child in node.children:
                _collect(child, source, out)
        return

    for child in node.children:
        _collect(child, source, out)


def _node_name(node: Node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return source[name_node.start_byte : name_node.end_byte].decode(
            "utf-8", errors="replace"
        )
    return "<anonymous>"


def _max_nesting(node: Node, depth: int = 0) -> int:
    deepest = depth
    for child in node.children:
        child_depth = depth + 1 if child.type in _NESTING_NODES else depth
        deepest = max(deepest, _max_nesting(child, child_depth))
    return deepest


def _parameter_count(node: Node) -> int:
    params = node.child_by_field_name("parameters")
    if params is None:
        return 0
    return sum(
        1
        for child in params.named_children
        if child.type not in {"comment", "type_annotation"}
    )


def analyse_file(file: SourceFile) -> list[Finding]:
    """Maintainability findings derived from the syntax tree."""
    grammar = _grammar_for(file.language)
    if grammar is None:
        return []

    try:
        parser = get_parser(grammar)
        tree = parser.parse(file.content.encode("utf-8"))
    except Exception:
        return []

    source = file.content.encode("utf-8")
    findings: list[Finding] = []

    def visit(node: Node) -> None:
        if node.type in _FUNCTION_NODES:
            name = _node_name(node, source)
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            length = end - start + 1

            if length > MAX_FUNCTION_LINES:
                findings.append(
                    _metric_finding(
                        file,
                        start,
                        end,
                        "long-function",
                        f"`{name}` fonksiyonu {length} satır",
                        f"Fonksiyon {length} satır uzunluğunda (eşik: "
                        f"{MAX_FUNCTION_LINES}). Tek sorumluluğa indirgenecek "
                        "şekilde bölünmesi test edilebilirliği artırır.",
                        Severity.LOW,
                    )
                )

            depth = _max_nesting(node)
            if depth > MAX_NESTING_DEPTH:
                findings.append(
                    _metric_finding(
                        file,
                        start,
                        end,
                        "deep-nesting",
                        f"`{name}` içinde {depth} seviye iç içe blok",
                        f"İç içe geçme derinliği {depth} (eşik: "
                        f"{MAX_NESTING_DEPTH}). Erken dönüş (guard clause) "
                        "kullanmak akışı düzleştirir.",
                        Severity.LOW,
                    )
                )

            params = _parameter_count(node)
            if params > MAX_PARAMETERS:
                findings.append(
                    _metric_finding(
                        file,
                        start,
                        start,
                        "long-parameter-list",
                        f"`{name}` {params} parametre alıyor",
                        f"Parametre sayısı {params} (eşik: {MAX_PARAMETERS}). "
                        "İlgili parametreleri bir veri sınıfında toplamayı düşünün.",
                        Severity.INFO,
                    )
                )

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return findings


def _metric_finding(
    file: SourceFile,
    line_start: int,
    line_end: int,
    category: str,
    title: str,
    explanation: str,
    severity: Severity,
) -> Finding:
    return Finding(
        file_path=file.path,
        line_start=line_start,
        line_end=line_end,
        severity=severity,
        category=category,
        title=title,
        explanation=explanation,
        origin=Origin.STATIC,
        tool=TOOL_NAME,
        rule_id=category.upper().replace("-", "_"),
        confidence=1.0,
    )


def analyse(files: list[SourceFile]) -> list[Finding]:
    findings: list[Finding] = []
    for file in files:
        findings.extend(analyse_file(file))
    return findings
