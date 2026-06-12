"""HMAC signing for the local storage backend's signed URLs."""
from __future__ import annotations

import hashlib
import hmac
import time

from django.conf import settings


def _key() -> bytes:
    return settings.STORAGE_SIGNING_KEY.encode("utf-8")


def sign(path: str, action: str, expires_at: int) -> str:
    message = f"{action}:{path}:{expires_at}".encode("utf-8")
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()


def make_token(path: str, action: str, ttl: int) -> tuple[int, str]:
    expires_at = int(time.time()) + ttl
    return expires_at, sign(path, action, expires_at)


def verify(path: str, action: str, expires_at: int, signature: str) -> bool:
    if int(time.time()) > expires_at:
        return False
    expected = sign(path, action, expires_at)
    return hmac.compare_digest(expected, signature)
