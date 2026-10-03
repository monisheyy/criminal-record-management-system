"""Validate a training dataset and write its dataset_manifest.json.

Run from backend/:
    python -m app.ml.build_manifest --dataset path/to/cases_v1.csv \
        --dataset-type authorized_historical --name "District case outcomes" \
        --version 1.0 --source "CRMS export 2020-2025, closed cases" \
        --owner "Records unit" --approval-ref "DPIA-2026-014" \
        --label-definition "Final charge-sheet offence category"

The manifest freezes the dataset: training refuses the CSV if its SHA-256 no
longer matches, and the dataset_type recorded here decides whether a model
trained on it may ever be activated. Only write a non-synthetic type for data
that has the legal approval named in --approval-ref.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ml.pipeline import (
    DATA_DIR, DATE_COLUMN, DatasetValidationError, FEATURE_COLUMNS, TARGET_COLUMNS,
    UNVALIDATED_DATASET_TYPES, load_training_dataset,
)

BUNDLED_DEMO_DATASET = (DATA_DIR / "demo_crime_training_v1.csv").resolve()
# Guidance thresholds, reported as warnings (the release gate is the hard check).
RECOMMENDED_ROWS_PER_CLASS = 100


def _duplicate_rows(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = [tuple(row) for row in csv.reader(handle)][1:]
    return sum(count - 1 for count in Counter(rows).values() if count > 1)


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    dataset = Path(args.dataset).resolve()
    if dataset == BUNDLED_DEMO_DATASET:
        raise SystemExit("Refusing to relabel the bundled synthetic demo dataset as real data.")
    if args.dataset_type in UNVALIDATED_DATASET_TYPES:
        raise SystemExit(f"--dataset-type must not be one of {sorted(UNVALIDATED_DATASET_TYPES)}; "
                         "those types are reserved for data that may not back an active model.")

    _, _, _, meta = load_training_dataset(dataset, verify_manifest=False)

    warnings = []
    small = {label: n for label, n in meta["crime_class_counts"].items() if n < RECOMMENDED_ROWS_PER_CLASS}
    if small:
        warnings.append(f"Crime classes with fewer than {RECOMMENDED_ROWS_PER_CLASS} rows (merge or drop them): {small}")
    duplicates = _duplicate_rows(dataset)
    if duplicates:
        warnings.append(f"{duplicates} exact duplicate rows; remove them unless they are genuinely separate cases.")
    if not meta["has_incident_dates"]:
        warnings.append(f"No '{DATE_COLUMN}' column: evaluation falls back to a random split instead of a "
                        "time-based holdout, which usually overstates real-world performance.")
    if not meta["slice_columns"]:
        warnings.append("No slice_* columns: per-group error analysis is limited to operational features.")
    heavily_missing = {col: n for col, n in meta["missing_counts"].items() if n > 0.3 * meta["rows"]}
    if heavily_missing:
        warnings.append(f"Columns more than 30% missing (median-imputed at training): {heavily_missing}")

    return {
        "dataset_name": args.name,
        "dataset_version": args.version,
        "dataset_type": args.dataset_type,
        "rows": meta["rows"],
        "feature_columns": FEATURE_COLUMNS,
        "target_columns": TARGET_COLUMNS,
        "optional_columns": ([DATE_COLUMN] if meta["has_incident_dates"] else [])
                            + [f"slice_{name}" for name in meta["slice_columns"]],
        "incident_date_range": meta.get("incident_date_range"),
        "crime_class_counts": meta["crime_class_counts"],
        "gang_class_counts": meta["gang_class_counts"],
        "missing_counts": meta["missing_counts"],
        "sha256": meta["sha256"],
        "source": args.source,
        "owner": args.owner,
        "legal_approval_reference": args.approval_ref,
        "label_definition": args.label_definition,
        "file_name": dataset.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1",
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None,
                        help="Manifest path (default: dataset_manifest.json next to the dataset)")
    parser.add_argument("--dataset-type", required=True, help="e.g. authorized_historical")
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", required=True, help="Where the rows came from and how they were selected")
    parser.add_argument("--owner", required=True, help="Accountable data owner")
    parser.add_argument("--approval-ref", required=True, help="Legal approval / DPIA reference")
    parser.add_argument("--label-definition", required=True, help="What crime_type means, e.g. final verified charge")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing manifest")
    args = parser.parse_args()

    output = (args.output or Path(args.dataset).resolve().parent / "dataset_manifest.json").resolve()
    if output.exists() and not args.force:
        print(f"{output} already exists; pass --force to replace it.", file=sys.stderr)
        return 1
    try:
        manifest = build_manifest(args)
    except (DatasetValidationError, FileNotFoundError) as exc:
        print(f"Dataset is not valid for training: {exc}", file=sys.stderr)
        return 1
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    for warning in manifest["warnings"]:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
