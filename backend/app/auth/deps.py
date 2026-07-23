"""Request-scoped auth dependencies.

`get_owned_review` is the single place ownership is enforced. Route handlers
must reach reviews and their children through it rather than querying by id -
that is what keeps one user out of another user's data.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.tokens import TokenError, TokenType, decode_token
from app.db.models import Review, User

_bearer = HTTPBearer(auto_error=False, description="Access token")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        user_id = decode_token(credentials.credentials, TokenType.ACCESS)
    except TokenError as exc:
        raise _UNAUTHORIZED from exc

    user = await User.get(PydanticObjectId(user_id))
    if user is None:
        raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_owned_review(review_id: PydanticObjectId, user: CurrentUser) -> Review:
    """Fetch a review that belongs to the caller.

    A review owned by somebody else yields 404, not 403, so the endpoint does
    not confirm that the id exists.
    """
    review = await Review.find_one(Review.id == review_id, Review.user_id == user.id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )
    return review


OwnedReview = Annotated[Review, Depends(get_owned_review)]
