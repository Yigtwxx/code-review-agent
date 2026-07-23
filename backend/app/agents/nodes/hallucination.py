"""Filter model output that nothing supports, and check imports really exist.

Two distinct failure modes share this node because both are the model being
confidently wrong:

* a finding invented out of thin air - no tool saw it and the model itself was
  not sure. Below the confidence floor those are dropped and counted, and the
  count is reported rather than hidden.
* an import of a package that was never published, in the reviewed code or in a
  suggested fix.

Corroborated findings are never dropped here, whatever their confidence: a
deterministic tool already agreed with them.
"""

import logging

from app.agents.packages import find_unknown_packages
from app.agents.state import ReviewState
from app.events.bus import EventType, emit
from app.schemas.finding import Category, Finding, Layer, Lens, Origin, Severity

logger = logging.getLogger(__name__)

STAGE = "hallucination_check"

#: An uncorroborated agent finding below this confidence is not worth a
#: reviewer's attention, and is our proxy metric for hallucination rate.
CONFIDENCE_FLOOR = 0.45

TOOL_NAME = "dependency-check"


async def hallucination_check(state: ReviewState) -> dict:
    review_id = state["review_id"]
    findings = state.get("findings", [])

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=STAGE,
        message="Düşük güvenli bulgular ve var olmayan bağımlılıklar kontrol ediliyor",
    )

    kept: list[Finding] = []
    suppressed = 0
    for finding in findings:
        if _is_unsupported(finding):
            suppressed += 1
            logger.debug(
                "Suppressed %s at %s:%d (confidence %.2f)",
                finding.category,
                finding.file_path,
                finding.line_start,
                finding.confidence,
            )
            continue
        kept.append(finding)

    kept.extend(await _dependency_findings(state))

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=(
            f"{suppressed} düşük güvenli bulgu elendi"
            if suppressed
            else "Elenen bulgu yok"
        ),
        suppressed=suppressed,
        kept=len(kept),
    )

    return {"findings": kept, "suppressed_low_confidence": suppressed}


def _is_unsupported(finding: Finding) -> bool:
    if finding.origin is not Origin.LLM:
        return False  # static evidence, or already corroborated
    return finding.confidence < CONFIDENCE_FLOOR


async def _dependency_findings(state: ReviewState) -> list[Finding]:
    unknown = await find_unknown_packages(state["files"])
    findings: list[Finding] = []

    for path, packages in unknown.items():
        file = next((f for f in state["files"] if f.path == path), None)
        if file is None:
            continue
        for name, ecosystem in packages:
            line = _import_line(file.content, name)
            findings.append(
                Finding(
                    file_path=path,
                    line_start=line,
                    line_end=line,
                    severity=Severity.MEDIUM,
                    category=Category.UNPINNED_DEPENDENCY,
                    title=f"`{name}` paketi {ecosystem} kayıtlarında bulunamadı",
                    explanation=(
                        f"`{name}` içe aktarılıyor ancak {ecosystem} üzerinde böyle "
                        "bir paket yok. Ya isim yanlış yazılmış, ya paket özel bir "
                        "kayıt defterinde, ya da var olmayan bir kütüphane "
                        "(halüsinasyon). Kurulum bu haliyle başarısız olur; "
                        "benzer isimli bir paketin devralınmış olma ihtimali de "
                        "tedarik zinciri riski taşır."
                    ),
                    origin=Origin.STATIC,
                    tool=TOOL_NAME,
                    rule_id="DEP001",
                    layer=Layer.CONFIG_INFRA,
                    lens=Lens.SECURITY,
                    confidence=0.8,
                )
            )
    return findings


def _import_line(content: str, package: str) -> int:
    """Best-effort line number of the import that mentions `package`."""
    stem = package.split("/")[0].lstrip("@")
    for number, line in enumerate(content.splitlines(), start=1):
        if ("import" in line or "require" in line) and stem in line:
            return number
    return 1
