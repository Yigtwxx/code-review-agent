"""Benchmark CLI: run the matrix, score it, write results, fill the report.

Run from the repo root with the backend uv environment (the harness package
lives at the repo root, `app` is put on the path by `benchmarks/__init__.py`)::

    uv run --project backend python -m benchmarks.run --help

Two phases:

* model comparison - each model reviewed against each language's vulnerable
  fixtures (detection, fix accuracy, latency) and clean fixtures (false
  positives), in hybrid mode.
* configuration comparison - one model run in static / llm / hybrid mode over
  the full fixture set, to answer "is the agent enough on its own".
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform
from datetime import datetime
from pathlib import Path

from benchmarks import metrics
from benchmarks.report_writer import (
    render_config_table,
    render_model_table,
    render_summary,
    splice_into_report,
)
from benchmarks.runner import GraphOutcome, load_paths, run_graph, run_static_only
from benchmarks.schema import (
    BenchmarkReport,
    CaseResult,
    DetectionResult,
    GroundTruth,
)

logger = logging.getLogger("benchmark")

REPO_ROOT = Path(__file__).resolve().parents[1]
VULN_ROOT = REPO_ROOT / "samples" / "vulnerable"
CLEAN_ROOT = REPO_ROOT / "samples" / "clean"
GROUND_TRUTH = VULN_ROOT / "ground_truth.json"
DOC_PATH = REPO_ROOT / "docs" / "sonuc-raporu.md"

DEFAULT_MODELS = [
    "qwen2.5-coder:7b-instruct-q4_K_M",
    "qwen3.5:9b",
    "qwen3.6:35b-a3b",
]
DEFAULT_CONFIG_MODEL = "qwen3.6:35b-a3b"

# Which fixture files stand in for each language, on both sides of the pairing.
# The Python pair uses different filenames (vulnerable_api / secure_api); the TS
# pairs share filenames across the vulnerable/clean trees.
LANGUAGE_FILES: dict[str, dict[str, list[str]]] = {
    "python": {
        "vulnerable": ["vulnerable_api.py"],
        "clean": ["secure_api.py"],
    },
    "typescript": {
        "vulnerable": ["backend/orders.service.ts", "frontend/ProfileCard.tsx"],
        "clean": ["backend/orders.service.ts", "frontend/ProfileCard.tsx"],
    },
}

# Which model rows appear in the report's model-comparison table.
MODEL_LANGUAGES: dict[str, list[str]] = {
    "qwen2.5-coder:7b-instruct-q4_K_M": ["python", "typescript"],
    "qwen3.5:9b": ["python"],
    "qwen3.6:35b-a3b": ["python", "typescript"],
}


def _outcome_to_detection(
    outcome: GraphOutcome, truth: GroundTruth, file_paths: set[str], tol: int
) -> DetectionResult:
    return metrics.detection(outcome.findings, truth.defects_for(file_paths), tol)


async def run_model_case(model: str, language: str, truth: GroundTruth) -> CaseResult:
    """One row of the model table: hybrid detection on vuln + FP on clean."""
    tol = truth.line_tolerance
    vuln_files = load_paths(VULN_ROOT, LANGUAGE_FILES[language]["vulnerable"])
    clean_files = load_paths(CLEAN_ROOT, LANGUAGE_FILES[language]["clean"])
    vuln_paths = {f.path for f in vuln_files}

    case = CaseResult(
        model=model, mode="hybrid", group=language, files=sorted(vuln_paths)
    )
    try:
        logger.info(
            "[%s / %s] detection run (%d files)", model, language, len(vuln_files)
        )
        vuln = await run_graph(model, vuln_files, disable_static=False)
        validated, total = metrics.fix_accuracy(vuln.patches)
        case.detection = _outcome_to_detection(vuln, truth, vuln_paths, tol)
        case.fix_validated, case.fix_total = validated, total
        case.finding_count = len(vuln.findings)
        case.origin_counts = metrics.origin_breakdown(vuln.findings)
        case.latency_ms = vuln.latency_ms
        case.latency_ms_per_file = vuln.latency_ms // max(1, len(vuln_files))

        logger.info(
            "[%s / %s] false-positive run (%d files)", model, language, len(clean_files)
        )
        clean = await run_graph(model, clean_files, disable_static=False)
        case.false_positives = metrics.false_positives(clean.findings)
    except Exception as exc:  # noqa: BLE001 - record, don't abort the matrix
        logger.exception("model case %s/%s failed", model, language)
        case.error = str(exc)
    return case


async def run_config_case(model: str, mode: str, truth: GroundTruth) -> CaseResult:
    """One row of the config table over the full fixture set."""
    tol = truth.line_tolerance
    all_vuln = list(truth.samples.keys())
    all_clean = [
        "secure_api.py",
        "backend/orders.service.ts",
        "frontend/ProfileCard.tsx",
    ]
    vuln_files = load_paths(VULN_ROOT, all_vuln)
    clean_files = load_paths(CLEAN_ROOT, all_clean)
    vuln_paths = {f.path for f in vuln_files}

    case = CaseResult(model=model, mode=mode, group="all", files=sorted(vuln_paths))
    try:
        logger.info("[config %s] detection run over full set", mode)
        if mode == "static":
            vuln = await run_static_only(vuln_files)
            clean = await run_static_only(clean_files)
        else:
            disable_static = mode == "llm"
            vuln = await run_graph(model, vuln_files, disable_static=disable_static)
            clean = await run_graph(model, clean_files, disable_static=disable_static)
        case.detection = _outcome_to_detection(vuln, truth, vuln_paths, tol)
        case.finding_count = len(vuln.findings)
        case.origin_counts = metrics.origin_breakdown(vuln.findings)
        case.latency_ms = vuln.latency_ms
        case.latency_ms_per_file = vuln.latency_ms // max(1, len(vuln_files))
        case.false_positives = metrics.false_positives(clean.findings)
        validated, total = metrics.fix_accuracy(vuln.patches)
        case.fix_validated, case.fix_total = validated, total
    except Exception as exc:  # noqa: BLE001
        logger.exception("config case %s failed", mode)
        case.error = str(exc)
    return case


async def run_matrix(args: argparse.Namespace) -> BenchmarkReport:
    truth = GroundTruth.load(GROUND_TRUTH)
    report = BenchmarkReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        hardware=args.hardware,
    )

    if not args.skip_models:
        for model in args.models:
            for language in MODEL_LANGUAGES.get(model, ["python"]):
                if args.languages and language not in args.languages:
                    continue
                report.model_cases.append(await run_model_case(model, language, truth))

    if not args.skip_config:
        for mode in args.modes:
            report.config_cases.append(
                await run_config_case(args.config_model, mode, truth)
            )
    return report


def write_results(report: BenchmarkReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.replace(":", "").replace("-", "")
    json_path = output_dir / f"{stamp}.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output_dir / f"{stamp}.md").write_text(render_summary(report), encoding="utf-8")
    return json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        type=lambda s: s.split(","),
        default=DEFAULT_MODELS,
        help="comma-separated Ollama model tags for the model-comparison table",
    )
    parser.add_argument("--config-model", default=DEFAULT_CONFIG_MODEL)
    parser.add_argument(
        "--languages",
        type=lambda s: s.split(","),
        default=[],
        help="restrict to these languages (default: all)",
    )
    parser.add_argument(
        "--modes",
        type=lambda s: s.split(","),
        default=["static", "llm", "hybrid"],
        help="configurations for the config-comparison table",
    )
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-config", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "benchmarks" / "results"
    )
    parser.add_argument(
        "--update-report",
        action="store_true",
        help=f"splice the filled tables into {DOC_PATH.name}",
    )
    parser.add_argument(
        "--hardware",
        default=f"{platform.machine()} · {platform.system()} {platform.release()}",
    )
    return parser.parse_args()


async def _amain() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = parse_args()
    report = await run_matrix(args)

    json_path = write_results(report, args.output)
    logger.info("results written to %s", json_path)

    print("\n=== Model karşılaştırması ===\n")
    print(render_model_table(report.model_cases))
    print("\n=== Yalnızca statik / LLM / hibrit ===\n")
    print(render_config_table(report.config_cases))

    if args.update_report and report.model_cases and report.config_cases:
        doc = DOC_PATH.read_text(encoding="utf-8")
        DOC_PATH.write_text(splice_into_report(doc, report), encoding="utf-8")
        logger.info("report updated: %s", DOC_PATH)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
