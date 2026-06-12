"""
Supabase Storage backend (private bucket) for staging/production.

Implemented with plain REST calls against the Storage API using the server-side
service-role key (never exposed to the browser):

* Signed upload  — POST /storage/v1/object/upload/sign/{bucket}/{path}
                   the browser then PUTs the file to the returned token URL.
* Signed download— POST /storage/v1/object/sign/{bucket}/{path}
* Server up/download use the authenticated object endpoint with the service key.

See https://supabase.com/docs/reference/javascript/storage-from-createsigneduploadurl
"""
from __future__ import annotations

from pathlib import Path

import requests
from django.conf import settings

from .base import ObjectStat, SignedUpload, Storage

TIMEOUT = 30


class SupabaseStorage(Storage):
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        self.base = settings.SUPABASE_URL.rstrip("/")
        self.bucket = settings.STORAGE_BUCKET
        self.key = settings.SUPABASE_SERVICE_KEY

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.key}",
            "apikey": self.key,
        }
        if extra:
            headers.update(extra)
        return headers

    def _storage_url(self, suffix: str) -> str:
        return f"{self.base}/storage/v1/{suffix.lstrip('/')}"

    def create_signed_upload(self, path: str, content_type: str = "") -> SignedUpload:
        resp = requests.post(
            self._storage_url(f"object/upload/sign/{self.bucket}/{path}"),
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        # Response contains a relative `url` like "/object/upload/sign/<bucket>/<path>?token=..."
        signed = resp.json()["url"].lstrip("/")
        # Keep the browser PUT minimal (only Content-Type) so the cross-origin
        # preflight stays simple; paths are unique per run so no upsert is needed.
        headers = {"Content-Type": content_type} if content_type else {}
        return SignedUpload(
            url=self._storage_url(signed),
            method="PUT",
            headers=headers,
            expires_in=2 * 60 * 60,  # Supabase fixes upload URLs to 2 hours
        )

    def stat(self, path: str) -> ObjectStat:
        parent, _, name = path.rpartition("/")
        resp = requests.post(
            self._storage_url(f"object/list/{self.bucket}"),
            headers=self._headers({"Content-Type": "application/json"}),
            json={"prefix": parent, "search": name, "limit": 100},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        for item in resp.json():
            if item.get("name") == name:
                size = (item.get("metadata") or {}).get("size", 0)
                return ObjectStat(exists=True, size=int(size or 0))
        return ObjectStat(exists=False)

    def create_signed_download(self, path: str, filename: str = "") -> str:
        body = {"expiresIn": settings.STORAGE_SIGNED_URL_TTL}
        if filename:
            body["download"] = filename
        resp = requests.post(
            self._storage_url(f"object/sign/{self.bucket}/{path}"),
            headers=self._headers({"Content-Type": "application/json"}),
            json=body,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        signed = resp.json()["signedURL"].lstrip("/")
        return self._storage_url(signed)

    def download_to(self, path: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(
            self._storage_url(f"object/{self.bucket}/{path}"),
            headers=self._headers(),
            stream=True,
            timeout=TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    fh.write(chunk)

    def upload_file(self, path: str, src: Path, content_type: str = "application/octet-stream") -> None:
        with open(src, "rb") as fh:
            resp = requests.post(
                self._storage_url(f"object/{self.bucket}/{path}"),
                headers=self._headers({"Content-Type": content_type, "x-upsert": "true"}),
                data=fh,
                timeout=TIMEOUT,
            )
        resp.raise_for_status()

    # --- administrative helpers (used by check_supabase / setup) ---
    def ensure_bucket(self, public: bool = False) -> str:
        """Create the private bucket if it doesn't exist. Returns 'created' or 'exists'."""
        resp = requests.post(
            self._storage_url("bucket"),
            headers=self._headers({"Content-Type": "application/json"}),
            json={"id": self.bucket, "name": self.bucket, "public": public},
            timeout=TIMEOUT,
        )
        if resp.status_code in (200, 201):
            return "created"
        if resp.status_code == 409 or "already exists" in resp.text.lower():
            return "exists"
        resp.raise_for_status()
        return "exists"

    def delete(self, path: str) -> None:
        requests.delete(
            self._storage_url(f"object/{self.bucket}/{path}"),
            headers=self._headers(),
            timeout=TIMEOUT,
        )
