"""Assign files to architectural layers, deciding which agents will run."""

from collections import Counter

from app.agents.partition import partition
from app.agents.state import ReviewState
from app.events.bus import EventType, emit

STAGE = "partition"


async def partition_files(state: ReviewState) -> dict:
    review_id = state["review_id"]
    files = state["files"]

    await emit(review_id, EventType.NODE_STARTED, stage=STAGE, message="Katman ayrımı")

    grouped = partition(files)
    distribution = Counter(
        {layer.value: len(members) for layer, members in grouped.items()}
    )

    await emit(
        review_id,
        EventType.NODE_FINISHED,
        stage=STAGE,
        message=", ".join(f"{layer}: {count}" for layer, count in distribution.items()),
        distribution=dict(distribution),
    )

    # `partition` annotated each file in place with its layers.
    return {"files": files}
