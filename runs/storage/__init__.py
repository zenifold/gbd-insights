"""
Pluggable object-storage boundary.

Views and the worker depend only on the abstract :class:`Storage` interface;
the concrete backend is chosen by the ``STORAGE_BACKEND`` setting:

* ``local``    — filesystem adapter that emulates the two-step signed-URL upload
                 flow, so the whole app runs locally with no Supabase account.
* ``supabase`` — Supabase Storage (private bucket) for staging/production.

Both speak the same contract, so swapping backends needs no code changes.
"""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from .base import SignedUpload, Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    backend = settings.STORAGE_BACKEND
    if backend == "local":
        from .local import LocalStorage

        return LocalStorage()
    if backend == "supabase":
        from .supabase import SupabaseStorage

        return SupabaseStorage()
    raise ValueError(f"Unknown STORAGE_BACKEND: {backend!r}")


__all__ = ["get_storage", "Storage", "SignedUpload"]
