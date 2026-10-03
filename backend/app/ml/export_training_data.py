"""Export this system's own closed cases as a training dataset.

Run from backend/ (uses DATABASE_URL like the server):
    python -m app.ml.export_training_data --output /secure/data/cases_v1.csv

Each closed or archived case with a verified offence category and an incident
date becomes one row. Features are built with the same code as live
predictions (app.ml.model_inputs + the pipeline's feature extraction), so the
model is trained on exactly what it will see. Unrecorded facts are written as
blank cells and median-imputed, never guessed.

The file has the training schema plus ``incident_date`` (time-based holdout)
and ``slice_station`` (per-police-station error analysis). Next steps are in
docs/MODEL_TRAINING.md: freeze it with build_manifest, compare models, train.
Treat the output as sensitive personal data.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, selectinload

from app import models
from app.ml.model_inputs import model_input
from app.ml.pipeline import (
    CRMSMLPipeline, DATE_COLUMN, EXPECTED_CRIMES, EXPECTED_GANGS, FEATURE_COLUMNS, SLICE_PREFIX, TARGET_COLUMNS,
)

# Cases whose outcome is settled. Open cases have no verified label yet.
LABELLED_STATUSES = (models.CaseStatus.closed, models.CaseStatus.archived)
# Which linked person a case's features describe, most authoritative first.
# Witnesses are never used.
OFFENDER_ROLE_PRIORITY = ("convicted", "primary_offender", "accused", "accomplice", "suspect")
STATION_SLICE = f"{SLICE_PREFIX}station"
RECOMMENDED_ROWS_PER_CLASS = 100
MIN_ROWS = 100


def _offender(case: models.Case) -> Optional[models.Criminal]:
    ranked = [
        (OFFENDER_ROLE_PRIORITY.index(link.role), link.criminal_id, link.criminal)
        for link in case.criminals
        if link.role in OFFENDER_ROLE_PRIORITY and link.criminal is not None
    ]
    return min(ranked, key=lambda item: item[:2])[2] if ranked else None


def _cell(value: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{value:g}"


def build_rows(db: Session) -> Dict[str, Any]:
    """Return ``{"rows": [...], "skipped": Counter}`` for every usable case."""
    cases = (
        db.query(models.Case)
        .options(selectinload(models.Case.criminals).selectinload(models.CaseCriminal.criminal)
                 .selectinload(models.Criminal.gang))
        .filter(models.Case.status.in_(LABELLED_STATUSES))
        .order_by(models.Case.incident_date, models.Case.id)
        .all()
    )
    rows: List[Dict[str, str]] = []
    skipped: Counter = Counter()
    for case in cases:
        if case.crime_type not in EXPECTED_CRIMES:
            skipped["no verified crime category (blank, Other or Unclassified)"] += 1
            continue
        if case.incident_date is None:
            skipped["no incident date"] += 1
            continue
        criminal = _offender(case)
        gang = criminal.gang.name if criminal is not None and criminal.gang is not None else "None"
        if gang not in EXPECTED_GANGS:
            skipped[f"gang '{gang}' is not a model gang class"] += 1
            continue
        features = CRMSMLPipeline._extract_features(model_input(criminal, case), impute_missing=True)
        row = {name: _cell(value) for name, value in zip(FEATURE_COLUMNS, features)}
        row["crime_type"] = case.crime_type
        row["gang_label"] = gang
        row[DATE_COLUMN] = case.incident_date.isoformat()
        row[STATION_SLICE] = (case.fir_station or "").strip() or "unknown"
        rows.append(row)
    return {"rows": rows, "skipped": skipped}


def readiness(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Summarise whether the export is big and complete enough to train on."""
    classes = Counter(row["crime_type"] for row in rows)
    recorded = {
        name: round(100.0 * sum(1 for row in rows if row[name] != "") / len(rows), 1) if rows else 0.0
        for name in FEATURE_COLUMNS
    }
    warnings = []
    if len(rows) < MIN_ROWS:
        warnings.append(f"Only {len(rows)} usable cases; training needs at least {MIN_ROWS}.")
    small = sorted(name for name, count in classes.items() if count < RECOMMENDED_ROWS_PER_CLASS)
    if small:
        warnings.append(f"Under {RECOMMENDED_ROWS_PER_CLASS} cases for: {', '.join(small)}. "
                        "Collect more or merge rare categories.")
    absent = sorted(set(EXPECTED_CRIMES) - set(classes))
    if absent:
        warnings.append(f"No cases at all for: {', '.join(absent)}.")
    never = [name for name, pct in recorded.items() if pct == 0.0]
    if never:
        warnings.append(f"Never recorded (always imputed, carry no signal): {', '.join(never)}.")
    sparse = [name for name, pct in recorded.items() if 0.0 < pct < 50.0]
    if sparse:
        warnings.append(f"Recorded on fewer than half of cases: {', '.join(sparse)}. "
                        "Fill in the Incident facts on every case.")
    return {"rows": len(rows), "class_counts": dict(sorted(classes.items())),
            "recorded_percent": recorded, "warnings": warnings}


def write_csv(rows: List[Dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    header = FEATURE_COLUMNS + TARGET_COLUMNS + [DATE_COLUMN, STATION_SLICE]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", required=True, type=Path, help="CSV to write (keep it out of the repository)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing file")
    args = parser.parse_args(argv)
    if args.output.exists() and not args.force:
        print(f"{args.output} exists; pass --force to overwrite (and rebuild its manifest).", file=sys.stderr)
        return 2

    from app.database import SessionLocal
    db = SessionLocal()
    try:
        result = build_rows(db)
    finally:
        db.close()
    rows = result["rows"]
    report = readiness(rows)
    write_csv(rows, args.output)

    print(f"Wrote {report['rows']} rows to {args.output}")
    for reason, count in sorted(result["skipped"].items()):
        print(f"  skipped {count}: {reason}")
    print("Cases per crime category:")
    for name, count in report["class_counts"].items():
        print(f"  {name:<20} {count}")
    print("Feature recorded on % of rows:")
    for name, pct in report["recorded_percent"].items():
        print(f"  {name:<20} {pct}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    return 0 if report["rows"] >= MIN_ROWS else 1


if __name__ == "__main__":
    sys.exit(main())
