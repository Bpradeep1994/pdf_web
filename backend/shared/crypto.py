"""
Field-level encryption for sensitive data at rest (OWASP A02: Cryptographic Failures).
Fernet (AES-128-CBC + HMAC) with a key derived from SECRET_KEY. Values are prefixed
with 'enc:' so legacy plaintext rows keep working transparently during rollout.
"""
import os
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:"


def _fernet() -> Fernet:
    secret = os.getenv("SECRET_KEY", "dev-secret-change-me")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """Decrypt a stored value. Returns it unchanged if it isn't our ciphertext
    (legacy plaintext) so existing data is never broken."""
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return value
