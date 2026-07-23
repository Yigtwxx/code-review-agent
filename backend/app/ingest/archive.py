"""ZIP intake.

Archives arrive from untrusted users, so this module is deliberately paranoid:
nothing is written to disk, entry names are rejected rather than sanitised, and
both the entry count and the *uncompressed* total are capped so a zip bomb
cannot exhaust memory.
"""

import io
import zipfile
from pathlib import PurePosixPath

from app.config import settings
from app.ingest.detect import detect_language, is_probably_binary, should_skip
from app.schemas.source import SourceFile


class ArchiveError(ValueError):
    """The archive is malformed or violates an ingest limit."""


def _is_unsafe_name(name: str) -> bool:
    """Reject absolute paths, traversal and Windows drive-letter entries."""
    if name.startswith(("/", "\\")):
        return True
    parts = PurePosixPath(name).parts
    if not parts:
        return True
    if ":" in parts[0]:
        return True
    return ".." in parts


def extract_source_files(data: bytes) -> list[SourceFile]:
    """Read reviewable text files out of a ZIP archive held in memory."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("Not a valid ZIP archive") from exc

    infos = [info for info in archive.infolist() if not info.is_dir()]

    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > settings.max_upload_bytes * 20:
        raise ArchiveError(
            "Archive expands to an implausible size and was rejected as a zip bomb"
        )

    files: list[SourceFile] = []
    for info in infos:
        if len(files) >= settings.max_files_per_review:
            break
        # Symlink entries (mode 0o120000) could point outside the archive.
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            continue
        if _is_unsafe_name(info.filename) or should_skip(info.filename):
            continue
        if info.file_size > settings.max_file_bytes:
            continue

        raw = archive.read(info)
        if is_probably_binary(raw):
            continue
        language = detect_language(info.filename)
        if language is None:
            continue

        files.append(
            SourceFile(
                path=_normalise(info.filename),
                content=raw.decode("utf-8", errors="replace"),
                language=language,
            )
        )

    if not files:
        raise ArchiveError("Archive contained no reviewable source files")
    return files


def _normalise(name: str) -> str:
    """Drop the single wrapper directory GitHub-style archives add."""
    return name.lstrip("./")
