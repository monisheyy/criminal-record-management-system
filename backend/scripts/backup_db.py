"""Online backup, verification and restore for the AI-CRMS SQLite database.

Usage (from backend/):
    python -m scripts.backup_db backup  [--db acrms.db] [--out backups/]
    python -m scripts.backup_db verify  backups/acrms-20261002T120000Z.db
    python -m scripts.backup_db restore backups/acrms-20261002T120000Z.db [--db acrms.db] --yes

* ``backup`` uses SQLite's online backup API (safe while the app is running),
  runs ``PRAGMA integrity_check`` on the copy and writes a ``.sha256`` sidecar.
* ``verify`` re-checks the checksum, integrity and Alembic revision.
* ``restore`` verifies first, keeps a safety copy of the current database and
  only then replaces it. Stop the application before restoring.

PostgreSQL deployments should use ``pg_dump``/``pg_restore`` instead; see
docs/OPERATIONS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(path: Path) -> str:
    # sqlite3's own context manager only commits; closing() releases the file
    # handle, which Windows needs before the file can be replaced.
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]


def _revision(path: Path) -> Optional[str]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None


def backup(db_path: Path, out_dir: Path) -> Path:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = out_dir / f"{db_path.stem}-{stamp}.db"
    with closing(sqlite3.connect(db_path.as_posix())) as source, closing(sqlite3.connect(target.as_posix())) as dest:
        source.backup(dest)
    result = _integrity(target)
    if result != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Backup failed integrity check: {result}")
    Path(f"{target}.sha256").write_text(f"{_sha256(target)}  {target.name}\n", encoding="utf-8")
    return target


def verify(backup_path: Path) -> dict:
    sidecar = Path(f"{backup_path}.sha256")
    if not backup_path.is_file() or not sidecar.is_file():
        raise FileNotFoundError("Backup file or its .sha256 checksum is missing")
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    actual = _sha256(backup_path)
    if expected != actual:
        raise RuntimeError("Backup checksum mismatch: the file is corrupt or was modified")
    integrity = _integrity(backup_path)
    if integrity != "ok":
        raise RuntimeError(f"Backup failed integrity check: {integrity}")
    return {"sha256": actual, "integrity": integrity, "alembic_revision": _revision(backup_path)}


def restore(backup_path: Path, db_path: Path) -> Path:
    info = verify(backup_path)
    safety_copy = None
    if db_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safety_copy = db_path.with_name(f"{db_path.stem}.pre-restore-{stamp}.db")
        shutil.copy2(db_path, safety_copy)
    temp = db_path.with_name(f".{db_path.name}.restoring")
    shutil.copy2(backup_path, temp)
    temp.replace(db_path)
    if _integrity(db_path) != "ok":
        if safety_copy:
            shutil.copy2(safety_copy, db_path)
        raise RuntimeError("Restored database failed integrity check; previous database put back")
    print(f"Restored {backup_path.name} (revision {info['alembic_revision']}). Safety copy: {safety_copy}")
    return db_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--db", default="acrms.db")
    b.add_argument("--out", default="backups")
    v = sub.add_parser("verify")
    v.add_argument("backup")
    r = sub.add_parser("restore")
    r.add_argument("backup")
    r.add_argument("--db", default="acrms.db")
    r.add_argument("--yes", action="store_true", help="Confirm replacing the live database")
    args = parser.parse_args(argv)

    if args.command == "backup":
        print(backup(Path(args.db), Path(args.out)))
    elif args.command == "verify":
        print(verify(Path(args.backup)))
    elif args.command == "restore":
        if not args.yes:
            print("Refusing to restore without --yes (this replaces the live database).", file=sys.stderr)
            return 2
        restore(Path(args.backup), Path(args.db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
