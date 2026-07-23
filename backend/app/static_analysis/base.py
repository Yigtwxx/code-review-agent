"""Shared plumbing for the external analysers.

The submitted code is written to a throwaway directory because linters are
file-oriented, and is then handed only to *analysers* - it is never imported,
never executed, and the directory is removed when the review ends.
"""

import asyncio
import contextlib
import logging
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.schemas.source import SourceFile

logger = logging.getLogger(__name__)

#: Hard ceiling per external tool; a hung linter must not stall a review.
TOOL_TIMEOUT_SECONDS = 120


class ToolUnavailable(RuntimeError):
    """An analyser could not run - not installed, or it timed out.

    Distinct from "ran and found nothing", so a review can report honestly on
    which parts of its coverage were actually exercised.
    """


@dataclass(frozen=True)
class Workspace:
    """A temporary on-disk mirror of the files under review."""

    root: Path
    files: tuple[SourceFile, ...]

    def absolute(self, path: str) -> Path:
        return self.root / path

    def relative(self, absolute_path: str) -> str:
        """Map a tool-reported absolute path back to the submission path."""
        try:
            return str(Path(absolute_path).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return absolute_path

    def paths_for(self, languages: set[str]) -> list[Path]:
        return [
            self.absolute(f.path) for f in self.files if f.language.value in languages
        ]


@contextlib.contextmanager
def materialise(files: list[SourceFile]) -> Iterator[Workspace]:
    """Write `files` into a temporary directory for the duration of the block."""
    # `.resolve()` matters: on macOS TMPDIR is /var/folders/... which is a
    # symlink to /private/var/folders/.... Tools that canonicalise paths would
    # otherwise decide our files sit outside the workspace they were given.
    root = Path(tempfile.mkdtemp(prefix="cra-review-")).resolve()
    try:
        for file in files:
            target = root / file.path
            # Defence in depth: ingest already rejected traversal, but a path
            # escaping the workspace here would write outside the sandbox.
            if not target.resolve().is_relative_to(root.resolve()):
                logger.warning("Skipping out-of-tree path %s", file.path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content, encoding="utf-8")
        yield Workspace(root=root, files=tuple(files))
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def run_tool(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = TOOL_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    """Run an analyser process and capture its output.

    Raises `ToolUnavailable` when the binary is missing or the run times out.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolUnavailable(f"{argv[0]} is not installed") from exc

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise ToolUnavailable(f"{argv[0]} timed out after {timeout}s") from exc

    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )
