"""Produce and verify a corrected version of each affected file.

A suggested fix nobody checked is a liability, so every patch is put back
through the same deterministic tooling that found the defects:

1. it must still parse - a fix that breaks the syntax tree is rejected;
2. it must not introduce new security findings; and
3. the security findings it was meant to remove should actually be gone.

The patch is stored either way, with `validated` recording the verdict. That
flag is what the "fix accuracy" figure in the report is computed from, and it
is why the UI can distinguish a checked suggestion from an unchecked one.
"""

import difflib
import logging

from app.agents.llm import LlmUnavailable, structured
from app.agents.state import PatchResult, RefactorTask
from app.config import settings
from app.events.bus import EventType, emit
from app.prompts import render
from app.schemas.finding import (
    SECURITY_CATEGORIES,
    SEVERITY_ORDER,
    Finding,
    Severity,
)
from app.schemas.refactor import RefactorResult
from app.schemas.source import SourceFile
from app.static_analysis.ast_tool import parse_structure
from app.static_analysis.registry import run_all

logger = logging.getLogger(__name__)

STAGE = "refactor"

#: Model output sometimes arrives wrapped in a fence despite instructions.
_FENCE_PREFIXES = (
    "```python",
    "```typescript",
    "```javascript",
    "```tsx",
    "```ts",
    "```js",
    "```sql",
    "```yaml",
    "```json",
    "```",
)


async def refactor_file(task: RefactorTask) -> dict:
    review_id = task["review_id"]
    file = task["file"]
    findings = task["findings"]

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=STAGE,
        message=f"{file.path}: {len(findings)} bulgu düzeltiliyor",
        file_path=file.path,
    )

    try:
        result = await structured(
            RefactorResult,
            system=render("refactor_system.jinja2"),
            user=render(
                "refactor_user.jinja2",
                path=file.path,
                language=file.language.value,
                code=file.content,
                findings=[_prompt_view(f) for f in findings],
            ),
            model=task["llm_model"],
            # A whole file comes back, not a finding list.
            num_predict=settings.llm_refactor_num_predict,
        )
    except LlmUnavailable:
        raise
    except Exception as exc:
        logger.warning("Refactor failed for %s: %s", file.path, exc)
        await emit(
            review_id,
            EventType.NODE_FINISHED,
            stage=STAGE,
            message=f"{file.path}: düzeltme üretilemedi",
            file_path=file.path,
        )
        return {"patches": []}

    refactored = _strip_fences(result.refactored_code)
    if not refactored.strip() or refactored.strip() == file.content.strip():
        await emit(
            review_id,
            EventType.NODE_FINISHED,
            stage=STAGE,
            message=f"{file.path}: değişiklik yok",
            file_path=file.path,
        )
        return {"patches": []}

    validated, report = await _validate(file, refactored, findings)

    patch = PatchResult(
        file_path=file.path,
        refactored_code=refactored,
        unified_diff=_diff(file, refactored),
        addresses_findings=len(findings),
        validated=validated,
        validation_output=report,
        notes=result.notes,
    )

    await emit(
        review_id,
        EventType.PATCH,
        stage=STAGE,
        message=f"{file.path}: {'doğrulandı' if validated else 'doğrulanamadı'}",
        file_path=file.path,
        validated=validated,
        detail=report,
    )
    return {"patches": [patch]}


def _prompt_view(finding: Finding) -> dict:
    return {
        "title": finding.title,
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "severity": finding.severity.value,
        "category": finding.category,
        "explanation": finding.explanation,
        "suggested_fix": finding.suggested_fix,
    }


def _strip_fences(code: str) -> str:
    text = code.strip()
    for prefix in _FENCE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip("\n")
            break
    if text.endswith("```"):
        text = text[: -len("```")].rstrip()
    return text + "\n"


def _diff(file: SourceFile, refactored: str) -> str:
    return "".join(
        difflib.unified_diff(
            file.content.splitlines(keepends=True),
            refactored.splitlines(keepends=True),
            fromfile=f"a/{file.path}",
            tofile=f"b/{file.path}",
            n=3,
        )
    )


async def _validate(
    file: SourceFile, refactored: str, addressed: list[Finding]
) -> tuple[bool, str]:
    """Re-run the deterministic tooling against the patched file."""
    patched = file.model_copy(update={"content": refactored})

    if not parse_structure(file).parse_error and parse_structure(patched).parse_error:
        return False, "Düzeltilmiş kod ayrıştırılamıyor: sözdizimi hatası eklenmiş."

    before, after = await run_all([file]), await run_all([patched])
    before_counts = _serious_counts(before.findings)
    after_counts = _serious_counts(after.findings)

    introduced = sorted(
        category
        for category, count in after_counts.items()
        if count > before_counts.get(category, 0)
    )
    if introduced:
        return False, (
            "Düzeltme yeni güvenlik bulgusu ekledi: " + ", ".join(introduced[:5])
        )

    # Only categories a deterministic tool could see before can be checked
    # afterwards. A finding only the model raised leaves no measurable trace,
    # so claiming it was verified would be dishonest.
    targeted = {f.category for f in addressed if f.category in SECURITY_CATEGORIES}
    checkable = {c for c in targeted if before_counts.get(c, 0) > 0}
    unresolved = sorted(
        c for c in checkable if after_counts.get(c, 0) >= before_counts[c]
    )
    if unresolved:
        return False, (
            "Şu kategoriler düzeltilmiş kodda hâlâ aynı sayıda tespit ediliyor: "
            + ", ".join(unresolved)
        )

    resolved = sum(before_counts.values()) - sum(after_counts.values())
    unverifiable = len(targeted) - len(checkable)
    detail = (
        f"Ayrıştırma başarılı; {resolved} statik güvenlik bulgusu giderildi, "
        "yeni bulgu eklenmedi."
    )
    if unverifiable:
        detail += (
            f" {unverifiable} bulgu yalnızca ajan tarafından raporlandığı için "
            "statik araçlarla doğrulanamadı."
        )
    return True, detail


def _serious_counts(findings: list[Finding]) -> dict[str, int]:
    """Security findings per category, at MEDIUM severity or above.

    Low-severity rules that fire on a *construct* rather than a vulnerability
    (bandit's "you called subprocess") would otherwise mark a genuinely better
    version of the file as a regression.
    """
    counts: dict[str, int] = {}
    for finding in findings:
        if finding.category not in SECURITY_CATEGORIES:
            continue
        if SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[Severity.MEDIUM]:
            continue
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return counts
