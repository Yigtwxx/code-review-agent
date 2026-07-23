"""Live review progress over WebSocket.

Browsers cannot set an Authorization header when opening a WebSocket, so the
access token is passed as a query parameter. It is the same short-lived token
as the REST API and it is verified before the socket is accepted - an
unauthenticated or non-owning client is closed, not merely ignored.
"""

import asyncio
import contextlib
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.auth.tokens import TokenError, TokenType, decode_token
from app.db.models import Review, ReviewStatus
from app.events.bus import EventType, ReviewEvent, bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

#: Sent when nothing has happened for a while, so proxies do not time the
#: connection out mid-review.
HEARTBEAT_SECONDS = 20

WS_POLICY_VIOLATION = 1008


@router.websocket("/ws/reviews/{review_id}")
async def review_progress(
    websocket: WebSocket,
    review_id: str,
    token: str = Query(default="", description="Access token"),
) -> None:
    review = await _authorise(token, review_id)
    if review is None:
        await websocket.close(code=WS_POLICY_VIOLATION, reason="Not authorised")
        return

    await websocket.accept()

    # A review that already finished gets its terminal state immediately, so a
    # client that connects late is not left waiting for an event that has been
    # and gone.
    if review.status in (ReviewStatus.COMPLETED, ReviewStatus.FAILED):
        await websocket.send_text(_terminal_event(review).model_dump_json())
        await websocket.close()
        return

    try:
        async with bus.subscribe(review_id) as queue:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    await websocket.send_text('{"type":"heartbeat"}')
                    continue

                await websocket.send_text(event.model_dump_json())
                if event.type in (
                    EventType.REVIEW_COMPLETED,
                    EventType.REVIEW_FAILED,
                ):
                    break
    except WebSocketDisconnect:
        logger.debug("Client disconnected from review %s", review_id)
    except Exception:
        logger.exception("WebSocket error on review %s", review_id)
    finally:
        # Closing an already-closed socket is not an error worth surfacing.
        with contextlib.suppress(RuntimeError):
            await websocket.close()


async def _authorise(token: str, review_id: str) -> Review | None:
    """Return the review only if this token's owner owns it."""
    if not token:
        return None
    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except TokenError:
        return None

    try:
        object_id = PydanticObjectId(review_id)
    except Exception:
        return None

    return await Review.find_one(
        Review.id == object_id, Review.user_id == PydanticObjectId(user_id)
    )


def _terminal_event(review: Review) -> ReviewEvent:
    completed = review.status is ReviewStatus.COMPLETED
    return ReviewEvent(
        type=EventType.REVIEW_COMPLETED if completed else EventType.REVIEW_FAILED,
        review_id=str(review.id),
        stage="report",
        message=(
            f"{review.stats.total_findings} bulgu, risk skoru {review.risk_score}"
            if completed
            else (review.error or "İnceleme başarısız oldu")
        ),
        payload={
            "risk_score": review.risk_score,
            "finding_count": review.stats.total_findings,
            "duration_ms": review.duration_ms,
            "replayed": True,
        },
    )
