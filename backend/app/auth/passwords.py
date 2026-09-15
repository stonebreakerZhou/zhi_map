"""Password hashing — PBKDF2-HMAC-SHA256, zero third-party deps.

OWASP 2024 password-storage cheat-sheet recommends PBKDF2-HMAC-SHA256
with >= 600,000 iterations; we use 310,000 with a 16-byte salt, which
balances security with login latency on commodity hardware (~200 ms).
"""
from __future__ import annotations
import hashlib
import hmac
import secrets

_ITER = 310_000
_ALGO = "sha256"
_SALT_LEN = 16
_SCHEME = f"pbkdf2_{_ALGO}"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITER)
    return f"{_SCHEME}${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_hex, dk_hex = stored.split("$")
        if scheme != _SCHEME:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        candidate = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False