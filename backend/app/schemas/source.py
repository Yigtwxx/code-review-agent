"""Normalised representation of the code under review.

Uploads, pasted snippets and GitHub PR diffs all converge on `SourceFile` so
that every downstream stage - static analysis, partitioning, agents - has one
input shape to reason about.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    JAVASCRIPT = "javascript"
    JSX = "jsx"
    SQL = "sql"
    YAML = "yaml"
    JSON = "json"
    DOCKERFILE = "dockerfile"
    HTML = "html"
    CSS = "css"
    SHELL = "shell"
    OTHER = "other"


#: Extension -> language. Anything unlisted is rejected at ingest time; we only
#: accept text we can actually parse or scan.
EXTENSION_LANGUAGE: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".cts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".js": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".jsx": Language.JSX,
    ".sql": Language.SQL,
    ".yml": Language.YAML,
    ".yaml": Language.YAML,
    ".json": Language.JSON,
    ".html": Language.HTML,
    ".css": Language.CSS,
    ".scss": Language.CSS,
    ".sh": Language.SHELL,
    ".bash": Language.SHELL,
    ".zsh": Language.SHELL,
    ".env": Language.OTHER,
    ".toml": Language.OTHER,
    ".ini": Language.OTHER,
    ".cfg": Language.OTHER,
    ".conf": Language.OTHER,
    ".md": Language.OTHER,
}

#: Files without a useful extension that we still want to analyse.
FILENAME_LANGUAGE: dict[str, Language] = {
    "dockerfile": Language.DOCKERFILE,
    "makefile": Language.OTHER,
    ".env": Language.OTHER,
    ".npmrc": Language.OTHER,
    ".gitignore": Language.OTHER,
}


class DiffHunk(BaseModel):
    """A contiguous changed region, used to scope PR reviews to new code."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    #: Line numbers in the new file that were added or modified.
    changed_lines: list[int] = Field(default_factory=list)


class SourceFile(BaseModel):
    """One file of the submission, ready for analysis."""

    path: str
    content: str
    language: Language
    #: Filled by the partition node; a file may legitimately span two layers.
    layers: list[str] = Field(default_factory=list)
    #: Present only for PR/CI reviews. `None` means "review the whole file".
    hunks: list[DiffHunk] | None = None
    #: True when the file exceeded `max_file_bytes` and was cut short.
    truncated: bool = False

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1

    @property
    def changed_lines(self) -> set[int] | None:
        """Union of all changed lines, or None when the whole file is in scope."""
        if self.hunks is None:
            return None
        lines: set[int] = set()
        for hunk in self.hunks:
            lines.update(hunk.changed_lines)
        return lines

    def numbered(self, start: int = 1, end: int | None = None) -> str:
        """Render the file with line numbers so the model can cite locations."""
        rows = self.content.splitlines()
        end = len(rows) if end is None else min(end, len(rows))
        width = len(str(end))
        return "\n".join(f"{n:>{width}} | {rows[n - 1]}" for n in range(start, end + 1))
