"""Password hashing and token generation shared by recruiter and candidate auth.

Stdlib pbkdf2_hmac instead of adding a dependency (bcrypt/passlib) — sufficient
for an MVP with a handful of accounts per role.
"""

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, _, expected_hex = password_hash.partition(":")
    if not salt or not expected_hex:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected_hex)


def generate_token() -> str:
    return secrets.token_urlsafe(32)
