"""
Seeds a default admin user if no admin exists yet. Generates a strong
random password with `secrets` (cryptographically secure, not `random`)
and prints it once -- it's never stored anywhere in plaintext, including
in this script's own output history, so write it down immediately.

This is meant for *initial* setup only. The whole point of a randomly
generated, never-repeated password is defeated if it ends up sitting in
a committed file forever -- rotate it (or just create a second admin and
deactivate this one) once you've logged in.

Usage:
    uv run python -m app.auth.seed_admin
    uv run python -m app.auth.seed_admin --email someone@example.com
"""

import argparse
import secrets
import string

from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password

DEFAULT_EMAIL = "admin@example.com"


def generate_strong_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main(email: str = DEFAULT_EMAIL):
    with get_session() as session:
        existing_admin = session.query(User).filter_by(is_admin=True).first()
        if existing_admin is not None:
            print(f"An admin user already exists ({existing_admin.email}). "
                  f"Not creating another one -- delete it first if you really "
                  f"want to reseed, or create additional admins by hand instead.")
            return None

        existing_email = session.query(User).filter_by(email=email).one_or_none()
        if existing_email is not None:
            print(f"A user with email {email!r} already exists but isn't an "
                  f"admin. Pick a different --email, or promote that user "
                  f"to admin by hand instead.")
            return None

        password = generate_strong_password()
        user = User(email=email, password_hash=hash_password(password), is_admin=True)
        session.add(user)

    print("\n" + "=" * 60)
    print("Default admin user created.")
    print(f"  email:    {email}")
    print(f"  password: {password}")
    print("=" * 60)
    print("This password is shown ONCE and is not stored in plaintext "
          "anywhere. Log in and consider rotating it once you have.\n")
    return password


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a default admin user.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    args = parser.parse_args()
    main(email=args.email)
