"""Unified-diff parsing.

Only the *new* side matters: a pull-request review comments on the code as it
will exist after the merge, so we track which lines of the new file the patch
added or modified. Deleted lines have no line to attach a comment to.
"""

import re

from app.schemas.source import DiffHunk

_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
)


def parse_patch(patch: str) -> list[DiffHunk]:
    """Extract hunks and their changed new-file line numbers from a patch."""
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    new_line = 0

    for line in patch.splitlines():
        header = _HUNK_HEADER.match(line)
        if header is not None:
            current = DiffHunk(
                old_start=int(header["old_start"]),
                old_lines=int(header["old_lines"] or 1),
                new_start=int(header["new_start"]),
                new_lines=int(header["new_lines"] or 1),
            )
            hunks.append(current)
            new_line = current.new_start
            continue

        if current is None:
            continue  # preamble before the first hunk

        if line.startswith("+"):
            current.changed_lines.append(new_line)
            new_line += 1
        elif line.startswith("-"):
            pass  # removed from the old file; no new-file line
        elif line.startswith("\\"):
            pass  # "\ No newline at end of file"
        else:
            new_line += 1  # context line

    return hunks
