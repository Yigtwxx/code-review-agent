"""Turn a BenchmarkReport into markdown tables and splice them into the report.

The two tables in ``docs/sonuc-raporu.md`` section 2 are left with empty cells
until a real run fills them. This module renders those cells from a result set
and can rewrite the tables in place, matching them by their header row so the
splice survives edits elsewhere in the document.
"""

from __future__ import annotations

from benchmarks.schema import BenchmarkReport, CaseResult


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _detection_cell(case: CaseResult) -> str:
    if case.detection is None:
        return "—"
    d = case.detection
    return f"{d.matched}/{d.total} ({_pct(d.rate)})"


def _fix_cell(case: CaseResult) -> str:
    if case.fix_total == 0:
        return "—"
    return f"{case.fix_validated}/{case.fix_total} ({_pct(case.fix_accuracy)})"


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.0f} sn"


_LANG_LABEL = {"python": "Python", "typescript": "TypeScript"}
_MODE_LABEL = {
    "static": "Yalnızca statik analiz (LLM kapalı)",
    "llm": "Yalnızca LLM (statik kanıt verilmiyor)",
    "hybrid": "Hibrit (mevcut sistem)",
}


def render_model_table(cases: list[CaseResult]) -> str:
    header = (
        "| Model / Sistem | Test Edilen Dil | Bulunan Hata | Yanlış Alarm "
        "| Düzeltme Başarısı | İşlem Süresi |\n"
        "|---|---|---|---|---|---|"
    )
    rows = []
    for case in cases:
        lang = _LANG_LABEL.get(case.group, case.group)
        fp = "—" if case.false_positives is None else str(case.false_positives)
        rows.append(
            f"| `{case.model}` | {lang} | {_detection_cell(case)} | {fp} "
            f"| {_fix_cell(case)} | {_seconds(case.latency_ms_per_file)} |"
        )
    return header + "\n" + "\n".join(rows)


def render_config_table(cases: list[CaseResult]) -> str:
    header = (
        "| Yapılandırma | Detection Rate | False Positive | Süre |\n|---|---|---|---|"
    )
    rows = []
    for case in cases:
        label = _MODE_LABEL.get(case.mode, case.mode)
        fp = "—" if case.false_positives is None else str(case.false_positives)
        detection = _detection_cell(case)
        rows.append(f"| {label} | {detection} | {fp} | {_seconds(case.latency_ms)} |")
    return header + "\n" + "\n".join(rows)


def render_summary(report: BenchmarkReport) -> str:
    """A standalone markdown snapshot for benchmarks/results/."""
    parts = [
        "# Benchmark sonuçları\n",
        f"Üretildi: {report.generated_at}  ·  Donanım: {report.hardware}\n",
        "## Model karşılaştırması\n",
        render_model_table(report.model_cases),
        "\n## Yalnızca linter vs. yalnızca LLM vs. hibrit\n",
        render_config_table(report.config_cases),
        "",
    ]
    return "\n".join(parts)


def _replace_table(lines: list[str], header_startswith: str, table: str) -> list[str]:
    """Replace a markdown table identified by its header row, in place."""
    for i, line in enumerate(lines):
        if line.startswith(header_startswith):
            end = i
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            return lines[:i] + table.split("\n") + lines[end:]
    raise ValueError(f"table header not found: {header_startswith!r}")


def _replace_status_note(lines: list[str]) -> list[str]:
    """Swap the 'not yet complete' blockquote for a done note."""
    for i, line in enumerate(lines):
        if line.startswith("> **Durum:**"):
            end = i
            while end < len(lines) and lines[end].startswith(">"):
                end += 1
            note = [
                "> **Durum:** Model karşılaştırmalı benchmark koşumu `benchmarks/`",
                "> harness'ı ile tamamlandı. Aşağıdaki değerler gerçek koşumdan gelir;",
                "> ham JSON çıktısı `benchmarks/results/` altındadır.",
            ]
            return lines[:i] + note + lines[end:]
    return lines


def splice_into_report(doc_text: str, report: BenchmarkReport) -> str:
    """Return `doc_text` with both tables and the status note filled in."""
    lines = doc_text.split("\n")
    lines = _replace_status_note(lines)
    lines = _replace_table(
        lines, "| Model / Sistem |", render_model_table(report.model_cases)
    )
    lines = _replace_table(
        lines,
        "| Yapılandırma | Detection Rate |",
        render_config_table(report.config_cases),
    )
    return "\n".join(lines)
