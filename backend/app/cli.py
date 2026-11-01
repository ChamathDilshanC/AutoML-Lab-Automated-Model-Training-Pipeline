"""Operator commands: `python -m app.cli <command>`.

There is no public sign-up. Accounts are created here, by someone with access to the server.
"""

import argparse
import getpass
import re
import sys
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.core.passwords import hash_password, validate_password_strength
from app.db import users as user_repo
from app.db.audit import record_audit
from app.db.session import SessionLocal, create_local_tables

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def create_user(username: str, password: str) -> str:
    """Create an account and return its user ID. Raises `ValueError` with a safe message."""
    if not USERNAME_PATTERN.match(username):
        raise ValueError("Username must be 3 to 64 characters: letters, digits, '_', '.' or '-'.")
    validate_password_strength(password)
    create_local_tables()
    with SessionLocal() as session:
        try:
            user = user_repo.create_user(session, username, hash_password(password))
        except IntegrityError:
            session.rollback()
            raise ValueError("That username is already taken.") from None
        record_audit(
            session, "user.create", actor_id=None, resource_type="user", resource_id=user.user_id
        )
        return user.user_id


def claim_legacy(username: str) -> dict[str, int]:
    """Give data created before accounts existed to a user."""
    create_local_tables()
    with SessionLocal() as session:
        user = user_repo.get_by_username(session, username)
        if user is None:
            raise ValueError("No such user.")
        return user_repo.claim_legacy_data(session, user.user_id)


def link_google(username: str, email: str) -> dict[str, int]:
    """Link a Google identity that has already signed in to a password user."""
    create_local_tables()
    with SessionLocal() as session:
        counts = user_repo.link_google_user(session, password_username=username, google_email=email)
        record_audit(session, "user.google_link", actor_id=None, resource_type="user")
        return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="create an account")
    create.add_argument("username")
    create.add_argument(
        "--password-stdin", action="store_true", help="read the password from standard input"
    )

    claim = commands.add_parser(
        "claim-legacy", help="assign data from before accounts existed to a user"
    )
    claim.add_argument("username")

    link = commands.add_parser(
        "link-google",
        help="merge a Google identity into an existing password user's data",
    )
    link.add_argument("username", help="existing password username")
    link.add_argument("email", help="email returned by the verified Google sign-in")

    args = parser.parse_args(argv)
    try:
        if args.command == "create-user":
            if args.password_stdin:
                password = sys.stdin.readline().rstrip("\r\n")
            else:
                password = getpass.getpass("Password: ")
                if password != getpass.getpass("Repeat password: "):
                    raise ValueError("The passwords do not match.")
            user_id = create_user(args.username, password)
            print(f"Created user {args.username.strip().lower()} ({user_id}).")
        elif args.command == "claim-legacy":
            counts = claim_legacy(args.username)
            print("Reassigned: " + ", ".join(f"{count} {name}" for name, count in counts.items()))
        else:
            counts = link_google(args.username, args.email)
            print("Linked: " + ", ".join(f"{count} {name}" for name, count in counts.items()))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
