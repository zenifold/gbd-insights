from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SignedUpload:
    """Everything the browser needs to PUT a file directly to object storage."""

    url: str
    method: str = "PUT"
    headers: dict = field(default_factory=dict)
    expires_in: int = 3600


@dataclass
class ObjectStat:
    exists: bool
    size: int = 0


class Storage:
    """Abstract object-storage backend."""

    def create_signed_upload(self, path: str, content_type: str = "") -> SignedUpload:
        raise NotImplementedError

    def stat(self, path: str) -> ObjectStat:
        """Return existence + size for an object (used to finalize an upload)."""
        raise NotImplementedError

    def create_signed_download(self, path: str, filename: str = "") -> str:
        """Return a short-lived URL the browser can GET to download an object."""
        raise NotImplementedError

    def download_to(self, path: str, dest: Path) -> None:
        """Download an object's bytes to a local file (worker side)."""
        raise NotImplementedError

    def upload_file(self, path: str, src: Path, content_type: str = "application/octet-stream") -> None:
        """Upload a local file to ``path`` (worker uploads the report artifact)."""
        raise NotImplementedError
