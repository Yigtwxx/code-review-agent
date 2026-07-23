"""Split a file into review-sized pieces.

Small files go to the model whole - context is what lets it spot a defect that
spans a function. Large files are split at function and class boundaries from
the syntax tree, so a chunk is always something a reviewer could reason about
on its own. Fixed-size windows would cut functions in half and produce findings
about code the model only half saw.
"""

from dataclasses import dataclass

from app.schemas.source import SourceFile
from app.static_analysis.ast_tool import parse_structure

#: A file at or below this many lines is reviewed in one call.
MAX_LINES_PER_CALL = 400

#: Chunks smaller than this are merged with their neighbour; a five-line chunk
#: costs a whole model call for very little signal.
MIN_CHUNK_LINES = 40


@dataclass(frozen=True)
class Chunk:
    line_start: int
    line_end: int
    #: Names of the units in this chunk, for logging and progress messages.
    label: str

    def numbered(self, file: SourceFile) -> str:
        return file.numbered(self.line_start, self.line_end)


def chunk_file(file: SourceFile) -> list[Chunk]:
    """Return the chunks to review for `file`, in line order."""
    total = file.line_count
    if total <= MAX_LINES_PER_CALL:
        return [Chunk(1, total, file.path)]

    structure = parse_structure(file)
    top_level = _top_level_units(structure.units)
    if not top_level:
        return _fixed_windows(total)

    chunks: list[Chunk] = []
    cursor = 1
    for unit in top_level:
        # Keep anything between units (imports, module-level code) attached to
        # the unit that follows it.
        start = min(cursor, unit.line_start)
        chunks.append(Chunk(start, unit.line_end, unit.name))
        cursor = unit.line_end + 1
    if cursor <= total:
        chunks.append(Chunk(cursor, total, "module tail"))

    return _merge_small(chunks)


def _top_level_units(units: list) -> list:
    """Keep outermost units only, so a class and its methods are not both sent."""
    ordered = sorted(units, key=lambda u: (u.line_start, -u.line_end))
    kept: list = []
    for unit in ordered:
        if kept and unit.line_end <= kept[-1].line_end:
            continue
        kept.append(unit)
    return kept


def _merge_small(chunks: list[Chunk]) -> list[Chunk]:
    merged: list[Chunk] = []
    for chunk in chunks:
        span = chunk.line_end - chunk.line_start + 1
        if (
            merged
            and span < MIN_CHUNK_LINES
            and (chunk.line_end - merged[-1].line_start + 1) <= MAX_LINES_PER_CALL
        ):
            previous = merged.pop()
            merged.append(
                Chunk(
                    previous.line_start,
                    chunk.line_end,
                    f"{previous.label}, {chunk.label}",
                )
            )
            continue
        merged.append(chunk)
    return merged


def _fixed_windows(total: int) -> list[Chunk]:
    """Fallback for files with no parseable structure, e.g. plain SQL or YAML."""
    return [
        Chunk(start, min(start + MAX_LINES_PER_CALL - 1, total), f"lines {start}+")
        for start in range(1, total + 1, MAX_LINES_PER_CALL)
    ]
