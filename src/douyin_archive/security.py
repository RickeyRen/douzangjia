import json
import re
from typing import Any

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken


class CookieCipher:
    """Authenticated encryption for browser state and local session payloads."""

    def __init__(self, master_key: str) -> None:
        self._fernet = Fernet(master_key.encode("ascii"))

    def encrypt(self, value: Any) -> bytes:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        return self._fernet.encrypt(payload)

    def decrypt(self, encrypted: bytes | str) -> Any:
        token = encrypted.encode("ascii") if isinstance(encrypted, str) else encrypted
        try:
            payload = self._fernet.decrypt(token)
        except InvalidToken as error:
            raise ValueError("encrypted value is invalid") from error
        return json.loads(payload)


class PasswordHasher:
    """Argon2id password hashing with a stable boolean verification API."""

    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return self._hasher.verify(encoded, password)
        except (InvalidHashError, VerificationError):
            return False


_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+", re.IGNORECASE)
_COOKIE_HEADER = re.compile(r"(cookie\s*:\s*)[^\r\n]+", re.IGNORECASE)
_SIGNED_VALUE = re.compile(
    r"(?i)(x-bogus|x-gorgon|x-khronos|signature|sessionid|token)=([^&\s]+)"
)


def redact_secrets(message: str) -> str:
    """Remove cookies, Douyin signatures, and signed URL query values from logs."""

    redacted = _URL_QUERY.sub(r"\1?[REDACTED]", message)
    redacted = _COOKIE_HEADER.sub(r"\1[REDACTED]", redacted)
    return _SIGNED_VALUE.sub(r"\1=[REDACTED]", redacted)
