"""
Filesystem storage backend for local development.

It emulates a real object store's two-step signed-URL flow: the browser receives
a short-lived HMAC-signed URL pointing at this app's own ``/_storage/*``
endpoints and PUTs/GETs the bytes there directly — exercising the exact same
client-side flow used against Supabase in production.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings

from .base import ObjectStat, SignedUpload, Storage
from .signing import make_token


def _safe_root_join(path: str) -> Path:
    root = Path(settings.LOCAL_STORAGE_ROOT).resolve()
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Path escapes storage root: {path!r}")
    return target


class LocalStorage(Storage):
    def _url(self, action: str, path: str, filename: str = "") -> str:
        ttl = settings.STORAGE_SIGNED_URL_TTL
        expires_at, signature = make_token(path, action, ttl)
        query = {"path": path, "exp": expires_at, "sig": signature}
        if filename:
            query["filename"] = filename
        base = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base}/_storage/{action}?{urlencode(query)}"

    def create_signed_upload(self, path: str, content_type: str = "") -> SignedUpload:
        headers = {"Content-Type": content_type} if content_type else {}
        return SignedUpload(
            url=self._url("upload", path),
            method="PUT",
            headers=headers,
            expires_in=settings.STORAGE_SIGNED_URL_TTL,
        )

    def stat(self, path: str) -> ObjectStat:
        target = _safe_root_join(path)
        if target.is_file():
            return ObjectStat(exists=True, size=target.stat().st_size)
        return ObjectStat(exists=False)

    def create_signed_download(self, path: str, filename: str = "") -> str:
        return self._url("download", path, filename=filename)

    def download_to(self, path: str, dest: Path) -> None:
        src = _safe_root_join(path)
        if not src.is_file():
            raise FileNotFoundError(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    def upload_file(self, path: str, src: Path, content_type: str = "application/octet-stream") -> None:
        target = _safe_root_join(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)

    # Used by the /_storage/upload endpoint to persist a streamed upload.
    # ``stream`` is any object with ``.read(size)`` (e.g. a Django HttpRequest),
    # read in chunks so large PUTs never load fully into memory. ``max_bytes``
    # caps the size; the partial file is removed and ValueError raised if exceeded.
    def write_stream(self, path: str, stream, chunk_size: int = 256 * 1024,
                     max_bytes: int | None = None) -> int:
        target = _safe_root_join(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with open(target, "wb") as fh:
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise ValueError("upload exceeds size limit")
                    fh.write(chunk)
        except ValueError:
            target.unlink(missing_ok=True)
            raise
        return size

    def open_for_read(self, path: str):
        return open(_safe_root_join(path), "rb")
