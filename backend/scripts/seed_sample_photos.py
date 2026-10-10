"""Add the illustrated sample mugshots to an existing demo database.

New demo databases get them automatically from ``seed_data.py``; run this
once (from ``backend/``) for a database seeded before they existed:

    python -m scripts.seed_sample_photos

Only records without a photo are touched. The portraits are synthetic
illustrations, not photos of real people.
"""
from app.database import SessionLocal
from app.utils.sample_photos import assign_sample_photos


def main() -> int:
    db = SessionLocal()
    try:
        count = assign_sample_photos(db)
        db.commit()
    finally:
        db.close()
    print(f"Added sample photos to {count} record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
