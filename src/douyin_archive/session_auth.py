from __future__ import annotations

import time

from .security import CookieCipher


class SessionCodec:
    """Validate encrypted local-admin session cookies for HTTP and WebSocket."""

    def __init__(self, cipher: CookieCipher) -> None:
        self.cipher = cipher

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            session = self.cipher.decrypt(token)
            return bool(
                isinstance(session, dict)
                and session.get("sub") == "admin"
                and session.get("expiresAt", 0) > int(time.time())
            )
        except (ValueError, AttributeError, TypeError):
            return False
