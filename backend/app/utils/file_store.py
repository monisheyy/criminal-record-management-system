"""Content-addressed storage for offender photos and evidence files.

Files are written once to ``<upload dir>/<sha256>`` and never modified, so
the SHA-256 recorded in the database (and in the audit trail) identifies the
exact bytes. Reads re-hash the file and refuse to serve it if it no longer
matches, which turns silent tampering or disk corruption into a visible,
audited integrity failure.

The type of an upload is decided from its first bytes, never from the
client-supplied filename or Content-Type.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile

UPLOAD_DIR = Path(
    os.getenv("AI_CRMS_UPLOAD_DIR") or (Path(__file__).resolve().parents[2] / "uploads")
).resolve()

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_EVIDENCE_BYTES = 20 * 1024 * 1024
_CHUNK = 1024 * 1024

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
EVIDENCE_TYPES = IMAGE_TYPES | {"image/gif", "application/pdf"}

EXTENSIONS = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/gif": "gif", "application/pdf": "pdf",
}


def sniff_content_type(head: bytes) -> Optional[str]:
    """Identify a supported file type from its magic bytes."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _path_for(sha256: str) -> Path:
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ValueError("invalid sha256")
    return UPLOAD_DIR / sha256


async def save_upload(upload: UploadFile, allowed_types: set, max_bytes: int) -> Tuple[str, str, int]:
    """Stream an upload to disk. Returns ``(sha256, content_type, size)``.

    Rejects empty, oversized and unsupported files with 413/415/422 before
    anything is stored.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    head = b""
    fd, tmp_name = tempfile.mkstemp(dir=UPLOAD_DIR, prefix=".incoming-")
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await upload.read(_CHUNK):
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File is larger than {max_bytes // (1024 * 1024)} MB")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="The uploaded file is empty")
        content_type = sniff_content_type(head)
        if content_type not in allowed_types:
            allowed = ", ".join(sorted(EXTENSIONS[t].upper() for t in allowed_types))
            raise HTTPException(status_code=415, detail=f"Unsupported file type; allowed: {allowed}")
        sha256 = digest.hexdigest()
        target = _path_for(sha256)
        if target.exists():
            os.unlink(tmp_name)
        else:
            os.replace(tmp_name, target)
            os.chmod(target, 0o440)
        return sha256, content_type, size
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def save_bytes(data: bytes, allowed_types: set) -> Tuple[str, str]:
    """Store in-memory bytes (used for bundled demo files). Returns ``(sha256, content_type)``."""
    content_type = sniff_content_type(data[:16])
    if content_type not in allowed_types:
        raise ValueError("unsupported file type")
    sha256 = hashlib.sha256(data).hexdigest()
    target = _path_for(sha256)
    if not target.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=UPLOAD_DIR, prefix=".incoming-")
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(tmp_name, target)
        os.chmod(target, 0o440)
    return sha256, content_type


def read_verified(sha256: str) -> Optional[bytes]:
    """Return the stored bytes, or ``None`` if missing or no longer matching the hash."""
    path = _path_for(sha256)
    if not path.is_file():
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        return None
    return data
