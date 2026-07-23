"""Ingest boundary: archive safety, limits and diff parsing."""

import io
import zipfile

import pytest

from app.ingest.archive import ArchiveError, extract_source_files
from app.ingest.detect import detect_language, should_skip
from app.ingest.diff import parse_patch
from app.ingest.service import IngestError, from_paste
from app.schemas.source import Language


def build_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_archive_yields_reviewable_files() -> None:
    data = build_zip({"src/app.py": "x = 1\n", "README.md": "# hi\n"})

    files = extract_source_files(data)

    assert {f.path for f in files} == {"src/app.py", "README.md"}


def test_archive_rejects_path_traversal_entries() -> None:
    data = build_zip({"../../etc/passwd.py": "x = 1\n", "ok.py": "y = 2\n"})

    files = extract_source_files(data)

    assert [f.path for f in files] == ["ok.py"]


def test_archive_rejects_absolute_paths() -> None:
    data = build_zip({"/etc/shadow.py": "x = 1\n", "ok.py": "y = 2\n"})

    assert [f.path for f in extract_source_files(data)] == ["ok.py"]


def test_archive_skips_vendored_directories() -> None:
    data = build_zip({"node_modules/left-pad/index.js": "x", "app.js": "y"})

    assert [f.path for f in extract_source_files(data)] == ["app.js"]


def test_archive_with_nothing_reviewable_is_rejected() -> None:
    with pytest.raises(ArchiveError, match="no reviewable source files"):
        extract_source_files(build_zip({"logo.png": "\x89PNG"}))


def test_corrupt_archive_is_rejected() -> None:
    with pytest.raises(ArchiveError, match="valid ZIP"):
        extract_source_files(b"this is not a zip file")


def test_paste_requires_a_recognisable_extension() -> None:
    with pytest.raises(IngestError, match="Cannot determine a language"):
        from_paste("notes", "print('hi')")


def test_paste_rejects_empty_content() -> None:
    with pytest.raises(IngestError, match="empty"):
        from_paste("a.py", "   \n")


def test_paste_strips_directory_traversal_from_the_filename() -> None:
    (file,) = from_paste("../../etc/passwd.py", "x = 1")

    assert file.path == "etc/passwd.py"
    assert file.language is Language.PYTHON


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.py", Language.PYTHON),
        ("a.tsx", Language.TSX),
        ("Dockerfile", Language.DOCKERFILE),
        ("dockerfile.prod", Language.DOCKERFILE),
        ("q.sql", Language.SQL),
        ("photo.png", None),
    ],
)
def test_language_detection(path: str, expected) -> None:
    assert detect_language(path) is expected


@pytest.mark.parametrize(
    "path",
    ["node_modules/x/index.js", "dist/bundle.js", "app.min.js", ".venv/lib/x.py"],
)
def test_generated_and_vendored_paths_are_skipped(path: str) -> None:
    assert should_skip(path) is True


def test_patch_parsing_reports_added_lines_of_the_new_file() -> None:
    patch = (
        "@@ -1,4 +1,6 @@\n"
        " import os\n"
        "-old = 1\n"
        "+new = 1\n"
        "+extra = 2\n"
        " keep = 3\n"
        " tail = 4\n"
    )

    (hunk,) = parse_patch(patch)

    assert hunk.new_start == 1
    assert hunk.changed_lines == [2, 3]


def test_patch_parsing_handles_several_hunks() -> None:
    patch = "@@ -1,2 +1,2 @@\n a\n+b\n@@ -20,2 +20,3 @@\n c\n+d\n"

    hunks = parse_patch(patch)

    assert len(hunks) == 2
    assert hunks[0].changed_lines == [2]
    assert hunks[1].changed_lines == [21]


def test_patch_without_hunks_yields_nothing() -> None:
    assert parse_patch("no hunks here") == []
