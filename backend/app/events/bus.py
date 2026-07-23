"""In-process pub/sub for live review progress.

A review runs as a background task in the same process that serves the
WebSocket, so an in-memory bus is enough - no broker, no extra moving part.
The trade-off is deliberate and bounded: progress events are ephemeral, and the
authoritative result is always the review document in MongoDB. A client that
connects late or reconnects re-reads the review rather than replaying events.

Subscriber queues are bounded. A browser tab that stops reading drops events
instead of growing the producer's memory without limit.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: Events buffered per subscriber before the oldest are dropped.
QUEUE_MAXSIZE = 256


class EventType(StrEnum):
    REVIEW_STARTED = "review_started"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    FINDING = "finding"
    PATCH = "patch"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_FAILED = "review_failed"


class ReviewEvent(BaseModel):
    type: EventType
    review_id: str
    #: Graph node or agent label, e.g. "BackendAgent · security".
    stage: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ReviewEvent]]] = defaultdict(set)

    async def publish(self, event: ReviewEvent) -> None:
        for queue in tuple(self._subscribers.get(event.review_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest so a stalled consumer loses history, not
                # the newest state.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    logger.debug("Dropped event for review %s", event.review_id)

    @asynccontextmanager
    async def subscribe(
        self, review_id: str
    ) -> AsyncIterator[asyncio.Queue[ReviewEvent]]:
        queue: asyncio.Queue[ReviewEvent] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers[review_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[review_id].discard(queue)
            if not self._subscribers[review_id]:
                del self._subscribers[review_id]


bus = EventBus()


async def emit(
    review_id: str,
    event_type: EventType,
    *,
    stage: str = "",
    message: str = "",
    **payload: Any,
) -> None:
    """Convenience wrapper used by graph nodes."""
    await bus.publish(
        ReviewEvent(
            type=event_type,
            review_id=review_id,
            stage=stage,
            message=message,
            payload=payload,
        )
    )
