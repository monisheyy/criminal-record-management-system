"""Attach the bundled illustrated mugshots to demo offender records.

The portraits in ``app/sample_photos`` are procedurally drawn by
``scripts/generate_sample_portraits.py``; none depicts a real person, and
each is stamped "SYNTHETIC ILLUSTRATION". They go through the normal
content-addressed file store, so they are served, hashed and verified exactly
like an uploaded photo.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.utils import file_store

PHOTO_DIR = Path(__file__).resolve().parents[1] / "sample_photos"


def _portraits(prefix: str) -> list[Path]:
    return sorted(PHOTO_DIR.glob(f"{prefix}-*.jpg"))


def assign_sample_photos(db: Session) -> int:
    """Give every offender without a photo a sample portrait matching their gender.

    Portraits are handed out in record order so each face is used once before
    any repeats. Returns the number of records updated; the caller commits.
    """
    pools = {"Female": _portraits("female"), "Male": _portraits("male")}
    if not pools["Male"]:
        return 0
    used = {"Female": 0, "Male": 0}
    stored: dict[Path, tuple[str, str]] = {}
    updated = 0
    for criminal in db.query(models.Criminal).order_by(models.Criminal.id):
        if criminal.photo_sha256:
            continue
        key = "Female" if criminal.gender == "Female" and pools["Female"] else "Male"
        path = pools[key][used[key] % len(pools[key])]
        used[key] += 1
        if path not in stored:
            stored[path] = file_store.save_bytes(path.read_bytes(), file_store.IMAGE_TYPES)
        criminal.photo_sha256, criminal.photo_content_type = stored[path]
        updated += 1
    return updated
