"""Build a clean source archive for hand-off or release.

    python scripts/package_release.py            # -> release/ai-crms-<commit>.zip
    python scripts/package_release.py --check    # only scan, exit 1 on problems

Only files tracked by git are packaged (so .env, local databases, caches,
node_modules, model artifacts and agent worktrees are never included), and
the result is scanned again for forbidden paths and obvious secrets before it
is written. Commit your changes first; uncommitted edits are not packaged.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_PATTERNS = [
    ".env", "*/.env", ".env.*", "*/.env.*", "*.db", "*.sqlite", "*.sqlite3", "*.pem", "*.key",
    "*/node_modules/*", "node_modules/*", "*/__pycache__/*", "*.pyc", "*/.pytest_cache/*",
    ".kilo/*", ".kilocode/*", "*/dist/*", "*.pkl", "backups/*", ".git/*",
]
ALLOWED = {".env.example"}
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "API secret key"),
    (re.compile(r"(?im)^\s*SECRET_KEY\s*=\s*(?!change-me)[^\s#]{32,}\s*$"), "SECRET_KEY value"),
]


def tracked_files() -> list[str]:
    output = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    return [name for name in output.decode("utf-8").split("\0") if name]


def problems_for(files: list[str]) -> list[str]:
    problems = []
    for name in files:
        if Path(name).name in ALLOWED:
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in FORBIDDEN_PATTERNS):
            problems.append(f"forbidden file: {name}")
            continue
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"possible {label} in: {name}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Scan only; do not write an archive")
    args = parser.parse_args(argv)

    files = tracked_files()
    problems = problems_for(files)
    if problems:
        print("Release blocked:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if args.check:
        print(f"OK: {len(files)} tracked files, no forbidden paths or obvious secrets.")
        return 0

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    archive = out_dir / f"ai-crms-{commit}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            zf.write(ROOT / name, arcname=f"ai-crms/{name}")
    print(f"Wrote {archive} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
