"""
Thin wrapper around werkzeug.security -- already a Flask dependency, so
this needs no extra crypto library. werkzeug's default hashing method
(scrypt as of recent Werkzeug versions) is a real, salted, slow hash;
this module exists so the rest of the app doesn't import werkzeug
directly and to keep the hashing scheme swappable from one place.
"""

from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(plain_password: str) -> str:
    return generate_password_hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, plain_password)
