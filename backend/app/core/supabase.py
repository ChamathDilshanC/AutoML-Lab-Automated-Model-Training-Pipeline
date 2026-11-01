"""Verification of Supabase Auth access tokens without network calls."""

import json
from typing import Any

import jwt

from app.core.config import Settings


class SupabaseTokenError(ValueError):
    """The supplied token is not an acceptable Supabase access token."""


def _issuer(settings: Settings) -> str | None:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None


def verify_supabase_token(token: str, settings: Settings) -> tuple[str, str]:
    """Return ``(subject, email)`` after strict, configured-algorithm verification."""
    algorithm = settings.supabase_jwt_algorithm
    issuer = _issuer(settings)
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != algorithm:
            raise SupabaseTokenError("Unexpected signing algorithm.")

        if settings.supabase_jwks:
            keys = json.loads(settings.supabase_jwks)
            jwk_set = keys.get("keys") if isinstance(keys, dict) else None
            if not isinstance(jwk_set, list):
                raise SupabaseTokenError("Invalid JWKS configuration.")
            matching = next((key for key in jwk_set if key.get("kid") == header.get("kid")), None)
            if matching is None:
                raise SupabaseTokenError("Signing key not found.")
            key: Any = jwt.PyJWK.from_dict(matching).key
        elif settings.supabase_jwt_secret:
            if algorithm != "HS256":
                raise SupabaseTokenError("A JWKS is required for this algorithm.")
            key = settings.supabase_jwt_secret.get_secret_value()
        else:
            raise SupabaseTokenError("Supabase verification is not configured.")

        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "sub", "aud", "email"]},
        )
    except SupabaseTokenError:
        raise
    except (jwt.PyJWTError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        raise SupabaseTokenError(f"Invalid Supabase token ({type(exc).__name__}).") from None

    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise SupabaseTokenError("Supabase token is missing identity claims.")
    return subject, email.strip().lower()
