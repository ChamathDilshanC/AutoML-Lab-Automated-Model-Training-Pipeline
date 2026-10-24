"""Password hashing with scrypt from the standard library (no extra dependency).

Stored format: `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>`. The parameters are stored with each
hash so they can be raised later without breaking existing passwords.
"""

import base64
import hashlib
import hmac
import secrets

N = 2**14
R = 8
P = 1
KEY_BYTES = 32
SALT_BYTES = 16
MAX_MEMORY = 64 * 1024 * 1024

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str) -> None:
    """Raise `ValueError` with a user-safe message if the password is not acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=MAX_MEMORY
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, N, R, P)
    encode = base64.b64encode
    return f"scrypt${N}${R}${P}${encode(salt).decode()}${encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash in constant time. A malformed hash never matches."""
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = _derive(password, salt, int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when a username does not exist, so a missing user costs the same time as a
# wrong password and the response does not reveal which usernames exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
