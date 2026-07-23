"""Language detection and ingest filtering."""

from pathlib import PurePosixPath

from app.schemas.source import EXTENSION_LANGUAGE, FILENAME_LANGUAGE, Language

#: Directories that are never worth reviewing - vendored or generated code.
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        "out",
        "coverage",
        "site-packages",
        ".idea",
        ".vscode",
    }
)

#: Generated or minified artefacts that would only produce noise.
SKIP_SUFFIXES = (".min.js", ".min.css", ".lock", ".map", ".snap")


def detect_language(path: str) -> Language | None:
    """Return the language for a path, or None if we do not analyse it."""
    name = PurePosixPath(path).name.lower()
    if name in FILENAME_LANGUAGE:
        return FILENAME_LANGUAGE[name]
    if name.startswith("dockerfile"):
        return Language.DOCKERFILE
    if name.startswith(".env"):
        return Language.OTHER

    suffix = PurePosixPath(name).suffix
    return EXTENSION_LANGUAGE.get(suffix)


def should_skip(path: str) -> bool:
    """True when a path is vendored, generated or otherwise not reviewable."""
    posix = PurePosixPath(path)
    if any(part in SKIP_DIRECTORIES for part in posix.parts):
        return True
    name = posix.name.lower()
    if name.endswith(SKIP_SUFFIXES):
        return True
    return detect_language(path) is None


def is_probably_binary(data: bytes) -> bool:
    """A NUL byte in the first block is the classic binary tell."""
    return b"\x00" in data[:8192]
