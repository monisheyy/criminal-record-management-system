"""Generate a reproducible evaluation/readiness report for the configured ML dataset.

Run from backend/: python -m app.ml.evaluate_dataset [--output path]
The command trains only in memory and never overwrites active model artifacts.
The bundled synthetic dataset must never be used to approve operational models.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.ml.pipeline import CRMSMLPipeline, FEATURE_COLUMNS, load_training_dataset


def build_report() -> dict[str, Any]:
    X, y_crime, y_gang, dataset = load_training_dataset()
    pipeline = CRMSMLPipeline()
    metrics = pipeline.train(X, y_crime, y_gang, save=False)
    crime_counts = Counter(map(str, y_crime))
    gang_counts = Counter(map(str, y_gang))
    is_demo = dataset.get("dataset_type") == "synthetic_demonstration"
    return {
        "report_type": "AI-CRMS ML evaluation and readiness audit",
        "dataset": dataset,
        "feature_count": len(FEATURE_COLUMNS),
        "target_distributions": {
            "crime_type": dict(sorted(crime_counts.items())),
            "gang_label": dict(sorted(gang_counts.items())),
        },
        "evaluation": {
            "method": metrics.get("evaluation_method"),
            "crime_classifier": metrics["crime_classifier"],
            "gang_predictor": metrics["gang_predictor"],
        },
        "readiness": {
            "dataset_is_synthetic_demo": is_demo,
            "operational_release_eligible": False,
            "reasons": [
                "The bundled dataset is synthetic demonstration data." if is_demo else "Dataset type requires independent review.",
                "Feature contract documents multiple inputs unavailable as structured, verified fields in the current application schema.",
                "The intended prediction target and time point must be formally approved before operational evaluation.",
                "Real-world representative validation, calibration, and fairness/error review are not established by this report.",
            ],
        },
        "disclaimer": "Metrics describe this dataset/split only. They do not establish real-world accuracy, dangerousness, guilt, or suitability for decisions about individuals.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()
    report = build_report()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote evaluation report: {args.output}")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
