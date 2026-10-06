from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


class TOTP:
    def __init__(self, secret: str, digits: int = 6, period: int = 30) -> None:
        self.secret = secret
        self.digits = digits
        self.period = period

    def _counter(self) -> int:
        return int(time.time() // self.period)

    def _code(self, counter: int) -> str:
        msg = counter.to_bytes(8, "big")
        digest = hmac.new(self.secret.encode("utf-8"), msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = ((digest[offset] & 0x7F) << 24) | ((digest[offset + 1] & 0xFF) << 16) | ((digest[offset + 2] & 0xFF) << 8) | (digest[offset + 3] & 0xFF)
        return str(code % (10 ** self.digits)).zfill(self.digits)

    def now(self) -> str:
        return self._code(self._counter())

    def verify(self, token: str, valid_window: int = 0) -> bool:
        try:
            current = self._counter()
            token = str(token).strip()
            for offset in range(-valid_window, valid_window + 1):
                if self._code(current + offset) == token:
                    return True
            return False
        except Exception:
            return False


__all__ = ["TOTP"]
