"""Read source files from disk.

Used by tests and the benchmark harness; the web API never touches the local
filesystem to build a review.
"""

from pathlib import Path

from app.config import settings
from app.ingest.detect import detect_language, is_probably_binary, should_skip
from app.schemas.source import SourceFile


def load_file(path: Path, *, base: Path | None = None) -> SourceFile | None:
    """Load one file, or None if it is not reviewable."""
    relative = str(path.relative_to(base)) if base else path.name
    language = detect_language(str(path))
    if language is None:
        return None

    raw = path.read_bytes()
    if is_probably_binary(raw):
        return None

    truncated = len(raw) > settings.max_file_bytes
    if truncated:
        raw = raw[: settings.max_file_bytes]

    return SourceFile(
        path=relative,
        content=raw.decode("utf-8", errors="replace"),
        language=language,
        truncated=truncated,
    )


def load_directory(root: Path) -> list[SourceFile]:
    """Recursively load every reviewable file under `root`."""
    files: list[SourceFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if should_skip(relative):
            continue
        source = load_file(path, base=root)
        if source is not None:
            files.append(source)
        if len(files) >= settings.max_files_per_review:
            break
    return files
