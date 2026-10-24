"""Access tokens: signed JWTs (HS256) carrying the user ID."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32


class TokenError(Exception):
    """The token is missing a claim, expired, or not signed with our key."""


_ephemeral_secret: str | None = None


def resolve_secret_key(settings: Settings) -> str:
    """The signing key. Configure `SECRET_KEY`; only the local environment may do without it.

    Without a configured key a random per-process key is used, so tokens stop working when the
    process restarts. Any other environment fails at start-up instead of running with a guessable
    or ephemeral key.
    """
    global _ephemeral_secret
    if settings.secret_key:
        if len(settings.secret_key) < MIN_SECRET_LENGTH:
            raise RuntimeError(f"SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters.")
        return settings.secret_key
    if settings.environment != "local":
        raise RuntimeError("SECRET_KEY must be set unless ENVIRONMENT is 'local'.")
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(48)
        logger.warning("SECRET_KEY is not set: using a temporary key; tokens reset on restart.")
    return _ephemeral_secret


def create_access_token(
    user_id: str, secret: str, minutes: int, now: datetime | None = None
) -> tuple[str, int]:
    """Return the token and its lifetime in seconds."""
    issued = now or datetime.now(UTC)
    lifetime = timedelta(minutes=minutes)
    claims = {"sub": user_id, "iat": issued, "exp": issued + lifetime}
    return jwt.encode(claims, secret, algorithm=ALGORITHM), int(lifetime.total_seconds())


def decode_access_token(token: str, secret: str) -> str:
    """Return the user ID, or raise `TokenError`.

    The algorithm list is fixed, so a token that names another algorithm (including `none`) is
    rejected, and `exp`, `iat` and `sub` are required.
    """
    try:
        claims = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub"]}
        )
    except jwt.PyJWTError:
        raise TokenError("invalid token") from None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("invalid subject")
    return subject
