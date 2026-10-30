"""Persistence for users. Usernames are matched case-insensitively (stored lower-case)."""

import uuid
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Dataset, Experiment, RegisteredModel, User

LEGACY_OWNER_ID = "local-user"  # the placeholder owner used before authentication existed


def normalize_username(username: str) -> str:
    return username.strip().lower()


def get_by_username(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == normalize_username(username)))


def get_by_id(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def get_by_auth_subject(session: Session, subject: str) -> User | None:
    return session.scalar(select(User).where(User.auth_subject == subject))


def create_google_user(session: Session, *, subject: str, email: str) -> User:
    """Create the local identity for a verified Supabase subject."""
    username = f"google_{sha256(subject.encode('utf-8')).hexdigest()[:48]}"
    user = User(
        user_id=f"us_{uuid.uuid4().hex}",
        username=username,
        password_hash="!",
        email=email,
        auth_subject=subject,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_user(session: Session, username: str, password_hash: str) -> User:
    """Insert a user. Raises `IntegrityError` if the username is taken."""
    user = User(
        user_id=f"us_{uuid.uuid4().hex}",
        username=normalize_username(username),
        password_hash=password_hash,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def claim_legacy_data(session: Session, user_id: str) -> dict[str, int]:
    """Give everything created under the placeholder owner to a real user."""
    counts: dict[str, int] = {}
    for label, table in (
        ("datasets", Dataset),
        ("experiments", Experiment),
        ("models", RegisteredModel),
    ):
        result = session.execute(
            update(table).where(table.owner_id == LEGACY_OWNER_ID).values(owner_id=user_id)
        )
        counts[label] = int(result.rowcount)  # type: ignore[attr-defined]
    session.commit()
    return counts


def link_google_user(
    session: Session, *, password_username: str, google_email: str
) -> dict[str, int]:
    """Merge a first Google-created identity into an existing password user."""
    password_user = get_by_username(session, password_username)
    google_user = session.scalar(
        select(User).where(
            User.email == google_email.strip().lower(), User.auth_subject.is_not(None)
        )
    )
    if password_user is None:
        raise ValueError("No such password user.")
    if google_user is None:
        raise ValueError("No Google user with that email was found. Sign in with Google first.")
    if password_user.user_id == google_user.user_id:
        raise ValueError("The password user and Google user are already linked.")
    if password_user.auth_subject is not None:
        raise ValueError("The password user is already linked to a Google identity.")

    counts: dict[str, int] = {}
    for label, table in (
        ("datasets", Dataset),
        ("experiments", Experiment),
        ("models", RegisteredModel),
    ):
        result = session.execute(
            update(table)
            .where(table.owner_id == google_user.user_id)
            .values(owner_id=password_user.user_id)
        )
        counts[label] = int(result.rowcount)  # type: ignore[attr-defined]

    linked_email = google_user.email
    google_subject = google_user.auth_subject
    assert linked_email is not None
    assert google_subject is not None
    session.delete(google_user)
    session.flush()
    password_user.email = linked_email
    password_user.auth_subject = google_subject
    session.commit()
    return counts
