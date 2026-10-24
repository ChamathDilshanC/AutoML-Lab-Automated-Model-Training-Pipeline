from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.passwords import DUMMY_HASH, verify_password
from app.core.security import get_current_user, unauthenticated
from app.core.tokens import create_access_token, resolve_secret_key
from app.db import users as user_repo
from app.db.audit import record_audit
from app.db.models import User
from app.db.session import get_session
from app.schemas.auth import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/login", response_model=TokenResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Exchange a username and password for a bearer token.

    Attempts are rate limited per client address. Unknown users and wrong passwords get the same
    answer in about the same time.
    """
    allowed, retry_after = request.app.state.login_limiter.check(
        f"login:{client_ip(request, settings.trusted_proxy_hops)}"
    )
    if not allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = user_repo.get_by_username(session, form.username)
    password_ok = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not user.is_active or not password_ok:
        record_audit(
            session,
            "auth.login",
            actor_id=user.user_id if user else None,
            outcome="failure",
            detail=f"username={user_repo.normalize_username(form.username)[:64]}",
        )
        raise unauthenticated("Incorrect username or password.")

    record_audit(
        session, "auth.login", actor_id=user.user_id, resource_type="user", resource_id=user.user_id
    )
    token, expires_in = create_access_token(
        user.user_id, resolve_secret_key(settings), settings.access_token_minutes
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse(user_id=user.user_id, username=user.username)
