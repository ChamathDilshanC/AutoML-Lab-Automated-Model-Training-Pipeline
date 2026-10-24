"""Authentication dependencies.

Every protected route depends on `get_owner_id`, which resolves the bearer token to a user and
returns that user's ID. Repositories filter by that ID, so a user can only reach their own
resources, and a foreign ID looks exactly like a missing one (404, not 403).
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.tokens import TokenError, decode_access_token, resolve_secret_key
from app.db import users as user_repo
from app.db.models import User
from app.db.session import get_session

_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def unauthenticated(message: str = "Authentication required.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message, headers=UNAUTHENTICATED_HEADERS)


def get_current_user(
    token: Annotated[str | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if not token:
        raise unauthenticated()
    try:
        user_id = decode_access_token(token, resolve_secret_key(settings))
    except TokenError:
        raise unauthenticated("Invalid or expired token.") from None
    user = user_repo.get_by_id(session, user_id)
    # A deleted or disabled user's tokens stop working immediately, not when they expire.
    if user is None or not user.is_active:
        raise unauthenticated("Invalid or expired token.")
    return user


def get_owner_id(user: Annotated[User, Depends(get_current_user)]) -> str:
    return user.user_id
