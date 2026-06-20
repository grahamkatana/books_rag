"""
Creates a new user with a real password, or resets an existing user's
password -- a workaround for the admin panel's password field not
reliably showing up on the create-user form.

Usage:
    uv run python -m app.auth.create_user --email someone@example.com --password "their password"
    uv run python -m app.auth.create_user --email someone@example.com --admin
    uv run python -m app.auth.create_user --email someone@example.com
        (no --password: generates a strong random one and prints it once)
    uv run python -m app.auth.create_user --email someone@example.com --password "new password" --update
        (user already exists: resets their password instead of erroring)
"""

import argparse
import secrets
import string

from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password


def generate_strong_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    parser = argparse.ArgumentParser(description="Create a user, or reset an existing user's password.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None,
                         help="If omitted, a strong random password is generated and printed once.")
    parser.add_argument("--admin", action="store_true", help="Make this user an admin.")
    parser.add_argument("--update", action="store_true",
                         help="If a user with this email already exists, reset their password "
                              "(and --admin status) instead of erroring out.")
    args = parser.parse_args()

    password = args.password or generate_strong_password()

    with get_session() as session:
        existing = session.query(User).filter_by(email=args.email).one_or_none()

        if existing is not None and not args.update:
            print(f"A user with email {args.email!r} already exists. "
                  f"Pass --update if you meant to reset their password.")
            return

        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.is_admin = args.admin
            action = "Updated"
        else:
            session.add(User(email=args.email, password_hash=hash_password(password), is_admin=args.admin))
            action = "Created"

    print("\n" + "=" * 60)
    print(f"{action} user.")
    print(f"  email:    {args.email}")
    print(f"  is_admin: {args.admin}")
    if not args.password:
        print(f"  password: {password}")
        print("  (generated -- shown once, not stored anywhere in plaintext)")
    print("=" * 60)


if __name__ == "__main__":
    main()