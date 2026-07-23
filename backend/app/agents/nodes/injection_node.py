"""Locate prompt-injection bait before the code reaches an agent."""

from app.agents.injection import scan
from app.agents.state import ReviewState
from app.events.bus import EventType, emit

STAGE = "injection_guard"


async def injection_guard(state: ReviewState) -> dict:
    review_id = state["review_id"]

    await emit(
        review_id,
        EventType.NODE_STARTED,
        stage=STAGE,
        message="Prompt injection taraması",
    )

    flags, findings = scan(state["files"])

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=(
            f"{len(flags)} dosyada şüpheli talimat metni"
            if flags
            else "Şüpheli talimat metni yok"
        ),
        flagged_files=sorted(flags),
    )

    # Appended here rather than through a reducer: this node is the only writer
    # of `static_findings` after the scan node, and the ordering is sequential.
    return {
        "injection_flags": flags,
        "static_findings": [*state.get("static_findings", []), *findings],
    }
