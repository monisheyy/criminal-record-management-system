"""Compare candidate crime-type models before training a release candidate.

Run from backend/: python -m app.ml.compare_models [--output report.json]

Only the development portion of the configured dataset is used: the same
locked holdout that `train()` evaluates on (the newest 20% of cases when the
dataset has incident dates) is excluded here, so choosing a model or a
calibration method never peeks at the final test set. Each candidate is scored
by cross-validation inside the development portion (forward-chaining
time-series folds when dates exist, stratified folds otherwise).

Use the result to pick AI_CRMS_CALIBRATION, then train the candidate from the
Model Governance page; the holdout result there is the one the gate judges.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

from app.config import settings
from app.ml.pipeline import (
    CALIBRATION_CV, CV_FOLDS, RANDOM_SEED, crime_estimator, expected_calibration_error,
    holdout_split, load_training_dataset,
)

CANDIDATES: dict[str, Callable[[], Any]] = {
    "majority_baseline": lambda: DummyClassifier(strategy="most_frequent"),
    "random_forest": crime_estimator,
    "random_forest+sigmoid": lambda: CalibratedClassifierCV(crime_estimator(), method="sigmoid", cv=CALIBRATION_CV),
    "random_forest+isotonic": lambda: CalibratedClassifierCV(crime_estimator(), method="isotonic", cv=CALIBRATION_CV),
    # Gradient boosting comparable to LightGBM without an extra dependency.
    "hist_gradient_boosting": lambda: HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=200, class_weight="balanced", random_state=RANDOM_SEED),
}


def _full_proba(model: Any, X: np.ndarray, n_classes: int) -> np.ndarray:
    """predict_proba over all classes, even those absent from a fold's training rows."""
    proba = np.zeros((len(X), n_classes))
    proba[:, model.classes_] = model.predict_proba(X)
    return proba


def _score_candidate(factory: Callable[[], Any], X: np.ndarray, y: np.ndarray, folds: list, n_classes: int) -> dict[str, Any]:
    scores: dict[str, list[float]] = {"macro_f1": [], "balanced_accuracy": [], "accuracy": [], "ece": []}
    errors = []
    for train_idx, test_idx in folds:
        model = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()),
                          ("model", factory())])
        try:
            model.fit(X[train_idx], y[train_idx])
        except ValueError as exc:  # e.g. a class too small for calibration folds
            errors.append(str(exc))
            continue
        proba = _full_proba(model, X[test_idx], n_classes)
        pred = proba.argmax(axis=1)
        scores["macro_f1"].append(f1_score(y[test_idx], pred, labels=np.arange(n_classes), average="macro", zero_division=0))
        scores["balanced_accuracy"].append(balanced_accuracy_score(y[test_idx], pred))
        scores["accuracy"].append(accuracy_score(y[test_idx], pred))
        scores["ece"].append(expected_calibration_error(y[test_idx], proba)["expected_calibration_error"])
    if not scores["macro_f1"]:
        return {"error": errors[0] if errors else "no folds could be evaluated"}
    result: dict[str, Any] = {"folds_evaluated": len(scores["macro_f1"])}
    for name, values in scores.items():
        result[f"{name}_mean"] = round(float(np.mean(values)), 4)
        result[f"{name}_std"] = round(float(np.std(values)), 4)
    if errors:
        result["skipped_folds"] = len(errors)
    return result


def build_report() -> dict[str, Any]:
    X, y_crime, _, dataset, context = load_training_dataset(with_context=True)
    encoder = LabelEncoder().fit(y_crime)
    y = encoder.transform(y_crime)
    dates = context["incident_dates"]
    dev_idx, holdout_idx, split_kind = holdout_split(y, dates)
    if dates is not None:
        dev_idx = dev_idx[np.argsort(dates[dev_idx], kind="stable")]
        folds = list(TimeSeriesSplit(n_splits=CV_FOLDS).split(dev_idx))
    else:
        min_count = int(np.bincount(y[dev_idx], minlength=len(encoder.classes_)).min())
        n_splits = max(2, min(CV_FOLDS, min_count))
        folds = list(StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_SEED).split(dev_idx, y[dev_idx]))
    X_dev, y_dev = X[dev_idx], y[dev_idx]

    results = {name: _score_candidate(factory, X_dev, y_dev, folds, len(encoder.classes_))
               for name, factory in CANDIDATES.items()}
    scored = {name: r for name, r in results.items() if "error" not in r and name != "majority_baseline"}
    baseline_bal_acc = results["majority_baseline"].get("balanced_accuracy_mean", 0.0)
    best = max(scored, key=lambda name: scored[name]["macro_f1_mean"]) if scored else None
    # Calibration should fix confidence without costing accuracy: only consider
    # forest variants whose macro-F1 is within one fold-std of the plain forest.
    plain = scored.get("random_forest")
    rf_variants = {name: r for name, r in scored.items() if name.startswith("random_forest") and plain
                   and r["macro_f1_mean"] >= plain["macro_f1_mean"] - plain["macro_f1_std"]}
    best_calibrated_rf = min(rf_variants, key=lambda name: rf_variants[name]["ece_mean"]) if rf_variants else None
    gate = settings.model_quality_gate.as_dict()
    best_result = scored.get(best, {}) if best else {}
    return {
        "report_type": "AI-CRMS crime-type model comparison (development data only)",
        "dataset": {key: dataset.get(key) for key in ("dataset_type", "dataset_version", "rows", "sha256")},
        "holdout": {"kind": split_kind, "rows_excluded": int(len(holdout_idx)),
                    "note": "Excluded here; judged once by the release gate when a candidate is trained."},
        "cv_scheme": "time_series" if dates is not None else "stratified",
        "development_rows": int(len(dev_idx)),
        "results": results,
        "summary": {
            "best_by_macro_f1": best,
            "best_beats_majority_baseline_balanced_accuracy": bool(
                best and best_result["balanced_accuracy_mean"] > baseline_bal_acc),
            "best_meets_gate_thresholds_in_cv": bool(
                best and best_result["macro_f1_mean"] >= gate["min_macro_f1"]
                and best_result["balanced_accuracy_mean"] >= gate["min_balanced_accuracy"]),
            "gate_thresholds": {"min_macro_f1": gate["min_macro_f1"], "min_balanced_accuracy": gate["min_balanced_accuracy"],
                                "max_expected_calibration_error": gate["max_expected_calibration_error"]},
            "lowest_ece_random_forest_variant": best_calibrated_rf,
            "suggested_AI_CRMS_CALIBRATION": (
                best_calibrated_rf.split("+", 1)[1] if best_calibrated_rf and "+" in best_calibrated_rf else "none"),
        },
        "notes": [
            "The release pipeline trains a Random Forest; if hist_gradient_boosting is clearly better on real data, "
            "switching the estimator in pipeline.crime_estimator() is the follow-up change.",
            "Differences smaller than the fold standard deviation are not meaningful.",
            "Majority-baseline ECE is high by construction (it is always 100% confident).",
        ],
    }


def _print_table(report: dict[str, Any]) -> None:
    print(f"Dataset: {report['dataset']['dataset_type']} v{report['dataset']['dataset_version']} "
          f"({report['development_rows']} development rows, {report['holdout']['rows_excluded']} locked holdout rows "
          f"excluded, {report['cv_scheme']} CV)\n")
    print(f"{'model':<26}{'macro-F1':>18}{'bal. acc':>18}{'ECE':>18}")
    for name, r in report["results"].items():
        if "error" in r:
            print(f"{name:<26}  error: {r['error']}")
            continue
        cells = [f"{r[f'{m}_mean']:.3f} +/- {r[f'{m}_std']:.3f}" for m in ("macro_f1", "balanced_accuracy", "ece")]
        print(f"{name:<26}" + "".join(f"{c:>18}" for c in cells))
    summary = report["summary"]
    gate = summary["gate_thresholds"]
    print(f"\nBest by macro-F1: {summary['best_by_macro_f1']} "
          f"(beats majority baseline on balanced accuracy: {summary['best_beats_majority_baseline_balanced_accuracy']})")
    print(f"Reaches gate thresholds in CV (macro-F1 >= {gate['min_macro_f1']}, balanced accuracy >= "
          f"{gate['min_balanced_accuracy']}): {summary['best_meets_gate_thresholds_in_cv']}")
    print(f"Suggested AI_CRMS_CALIBRATION={summary['suggested_AI_CRMS_CALIBRATION']} "
          f"(lowest ECE without losing macro-F1; gate requires ECE <= {gate['max_expected_calibration_error']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()
    report = build_report()
    _print_table(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
