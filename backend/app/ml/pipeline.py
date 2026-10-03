"""AI-CRMS machine-learning pipeline.

The runtime prediction path is intentionally kept compatible with the original
Random Forest artifacts and feature schema. Training now reads a versioned,
validated dataset from ``app/ml/data`` instead of generating rows in memory.

The bundled dataset is synthetic demonstration data only; it contains no real
criminal personal data and must not be presented as a production dataset.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import logging
import os
import pickle
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, make_scorer, roc_auc_score, accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit, cross_validate, train_test_split
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

logger = logging.getLogger("ai_crms.ml")

BASE_DIR = Path(__file__).resolve().parent
# Overridable so tests and multi-instance deployments never overwrite the
# active model artifacts of a developer's working copy.
MODEL_DIR = Path(os.getenv("AI_CRMS_MODEL_DIR") or (BASE_DIR / "saved_models")).resolve()
CANDIDATES_DIR = MODEL_DIR / "candidates"
DATA_DIR = BASE_DIR / "data"
# Point AI_CRMS_DATASET_PATH at an approved dataset to train on real data. Its
# manifest is read from AI_CRMS_DATASET_MANIFEST, else from the
# dataset_manifest.json next to the CSV (build one with app.ml.build_manifest).
DATASET_PATH = Path(os.getenv("AI_CRMS_DATASET_PATH") or (DATA_DIR / "india_crime_training_v1.csv")).resolve()
MANIFEST_PATH = Path(os.getenv("AI_CRMS_DATASET_MANIFEST") or (DATASET_PATH.parent / "dataset_manifest.json")).resolve()
METADATA_PATH = MODEL_DIR / "metadata.json"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
TEST_SIZE = 0.20
DATASET_VERSION = "1.0"
PIPELINE_VERSION = "2.0"
CV_FOLDS = 5
# Optional probability calibration of the crime classifier: none | sigmoid | isotonic.
# Choose it with evidence from `python -m app.ml.compare_models`, not by default.
CALIBRATION_METHODS = ("none", "sigmoid", "isotonic")
CALIBRATION_METHOD = (os.getenv("AI_CRMS_CALIBRATION") or "none").strip().lower()
CALIBRATION_CV = 3

# Reference date keeps feature extraction deterministic across calendar time.
RISK_REFERENCE_DATE = date(2026, 1, 1)

# Prototype decision-support score configuration. These weights are intentionally
# explicit and sum to 100 for the positive components. They are not clinically
# or legally validated risk-assessment weights.
RISK_SCORE_CONFIG = {
    "prior_convictions": {"weight": 20.0, "max_value": 5.0},
    "violence_history": {"weight": 20.0, "max_value": 5.0},
    "gang_probability": {"weight": 20.0},
    "crime_confidence": {"weight": 10.0},
    "wanted_status": {"weight": 15.0},
    "crime_severity": {"weight": 15.0},
    "incarcerated_adjustment": {"weight": -5.0},
}

CRIME_SEVERITY = {
    "Murder": 1.0, "Human Trafficking": 1.0, "Arms Trafficking": 1.0,
    "Kidnapping": 0.8, "Drug Trafficking": 0.8, "Robbery": 0.75,
    "Assault": 0.7, "Extortion": 0.6, "Money Laundering": 0.55,
    "Fraud": 0.5, "Arson": 0.5, "Burglary": 0.4, "Car Theft": 0.35,
    "Cybercrime": 0.35, "Vandalism": 0.2,
}

FEATURE_COLUMNS = [
    "prior_convictions", "age", "is_gang_member", "weapons_involved",
    "drug_involvement", "financial_motivation", "tech_involvement",
    "violence_history", "location_risk", "time_of_crime", "associates_count",
]
# Gang affiliation is the target for the gang model. `is_gang_member` is a direct
# proxy for that target and must not be included as a predictor for that model.
GANG_FEATURE_COLUMNS = [name for name in FEATURE_COLUMNS if name != "is_gang_member"]
GANG_FEATURE_INDICES = [FEATURE_COLUMNS.index(name) for name in GANG_FEATURE_COLUMNS]
TARGET_COLUMNS = ["crime_type", "gang_label"]
# Optional dataset columns that are never model inputs:
#  - incident_date (ISO 8601) switches evaluation to a time-based holdout
#    (train on older cases, test on the newest TEST_SIZE fraction);
#  - slice_<name> columns (e.g. slice_district) are categorical groups used only
#    for per-slice error analysis in subgroup_evaluation.
DATE_COLUMN = "incident_date"
SLICE_PREFIX = "slice_"
#  - reoffended_2y (0/1) is an observed outcome (re-arrested within two years
#    of the incident). When present, a learned danger-score model is trained on
#    it; otherwise the fixed-weight prototype score is used.
OUTCOME_COLUMN = "reoffended_2y"
# Case fields recorded by officers that map 1:1 onto model features.
CASE_INCIDENT_FEATURES = ("weapons_involved", "drug_involvement", "financial_motivation", "tech_involvement")
# Dataset types whose models may be trained and evaluated but never activated.
UNVALIDATED_DATASET_TYPES = frozenset({"synthetic_demonstration", "unknown", "external"})

from app.constants import CRIME_CATEGORIES, CRIME_TYPES, GANG_NAMES  # noqa: E402  (single source of truth)
EXPECTED_CRIMES = set(CRIME_TYPES)
EXPECTED_GANGS = set(GANG_NAMES) | {"None"}

NUMERIC_RANGES = {
    "prior_convictions": (0, 100), "age": (16, 100), "is_gang_member": (0, 1),
    "weapons_involved": (0, 1), "drug_involvement": (0, 1),
    "financial_motivation": (0, 1), "tech_involvement": (0, 1),
    "violence_history": (0, 100), "location_risk": (0, 1),
    "time_of_crime": (0, 23), "associates_count": (0, 1000),
}


class DatasetValidationError(ValueError):
    """Raised when the configured ML training dataset is invalid."""


class ArtifactIntegrityError(RuntimeError):
    """Raised when model artifacts do not match their recorded hashes/signature."""


ARTIFACT_FILES = ("crime_classifier.pkl", "gang_predictor.pkl", "encoders.pkl")
CALIBRATION_BINS = 10


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signing_key() -> Optional[bytes]:
    secret = os.getenv("SECRET_KEY")
    return secret.encode("utf-8") if secret and len(secret) >= 32 else None


def sign_artifact_hashes(hashes: Dict[str, str], model_version: str) -> Optional[str]:
    key = _signing_key()
    if key is None:
        return None
    message = json.dumps({"model_version": model_version, "artifacts": hashes}, sort_keys=True).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_artifacts(directory: Path, metadata: Dict[str, Any], *, require_signature: bool = False) -> Dict[str, Any]:
    """Check artifact files against recorded SHA-256 hashes and HMAC signature.

    Must run BEFORE unpickling: pickle files can execute arbitrary code, so an
    artifact that was swapped or tampered with must never be loaded.
    Returns a status dict; raises ArtifactIntegrityError on any mismatch.
    """
    recorded = metadata.get("artifact_sha256")
    if not recorded:
        if require_signature:
            raise ArtifactIntegrityError("Model artifacts have no recorded hashes; retrain a signed candidate")
        return {"status": "legacy_unsigned", "verified": False}
    for name in ARTIFACT_FILES:
        path = directory / name
        if not path.is_file():
            raise ArtifactIntegrityError(f"Missing model artifact: {name}")
        if not hmac.compare_digest(_file_sha256(path), str(recorded.get(name, ""))):
            raise ArtifactIntegrityError(f"Model artifact hash mismatch: {name}")
    expected = sign_artifact_hashes(recorded, str(metadata.get("model_version", "")))
    signature = metadata.get("artifact_signature")
    if expected is None or not signature or not hmac.compare_digest(expected, signature):
        raise ArtifactIntegrityError(
            "Model artifact signature is invalid (tampering, or SECRET_KEY changed since training). "
            "Retrain and activate a new candidate."
        )
    return {"status": "verified", "verified": True}


def expected_calibration_error(y_true: np.ndarray, proba: np.ndarray, bins: int = CALIBRATION_BINS) -> Dict[str, Any]:
    """Top-label ECE and multi-class Brier score on held-out data.

    ECE compares the model's stated confidence with its observed accuracy. A
    large value means the displayed "confidence" should not be read as a
    probability.
    """
    y_true = np.asarray(y_true, dtype=int)
    confidence = proba.max(axis=1)
    predicted = proba.argmax(axis=1)
    correct = (predicted == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    table = []
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (confidence >= low) & (confidence <= high) if index == 0 else (confidence > low) & (confidence <= high)
        count = int(mask.sum())
        if count == 0:
            continue
        accuracy = float(correct[mask].mean())
        mean_conf = float(confidence[mask].mean())
        ece += (count / len(y_true)) * abs(accuracy - mean_conf)
        table.append({"bin": [round(float(low), 2), round(float(high), 2)], "count": count,
                      "mean_confidence": round(mean_conf, 4), "accuracy": round(accuracy, 4)})
    one_hot = np.zeros_like(proba)
    one_hot[np.arange(len(y_true)), y_true] = 1.0
    brier = float(np.mean(np.sum((proba - one_hot) ** 2, axis=1)))
    return {"expected_calibration_error": round(float(ece), 6), "brier_score": round(brier, 6),
            "mean_confidence": round(float(confidence.mean()), 6), "reliability_table": table}


# Evaluation slices. The bundled dataset contains no protected attributes
# (e.g. ethnicity, religion, gender), so only operational/geographic proxies can
# be sliced here. Real deployments must add legally permissible subgroup
# columns to the evaluation set and extend this list (see docs/MODEL_CARD.md).
SUBGROUP_SLICES = {
    "age_band": ("age", [(16, 25, "16-24"), (25, 40, "25-39"), (40, 101, "40+")]),
    "gang_membership": ("is_gang_member", [(0, 0.5, "non-member"), (0.5, 1.01, "member")]),
    "location_risk_band": ("location_risk", [(0, 0.34, "low"), (0.34, 0.67, "medium"), (0.67, 1.01, "high")]),
    "time_of_day": ("time_of_crime", [(6, 18, "day 06-17"), (18, 24, "evening 18-23"), (0, 6, "night 00-05")]),
}
MIN_SLICE_SAMPLES = 10


def subgroup_evaluation(
    X_raw: np.ndarray, y_true: np.ndarray, y_pred: np.ndarray, classes: Sequence[str],
    categorical_slices: Optional[Dict[str, np.ndarray]] = None,
) -> Dict[str, Any]:
    """Per-slice accuracy / macro-F1 with sample sizes and the worst-case gap.

    ``categorical_slices`` maps a slice name to one group label per row (from
    the dataset's ``slice_*`` columns); blank labels are left out of every group.
    """
    labels = np.arange(len(classes))
    overall = float(accuracy_score(y_true, y_pred)) if len(y_true) else 0.0
    report: Dict[str, Any] = {"overall_accuracy": overall, "min_slice_samples": MIN_SLICE_SAMPLES, "slices": {}}
    worst_gap = 0.0
    masks_by_slice: Dict[str, List[Tuple[str, np.ndarray]]] = {}
    for slice_name, (feature, bands) in SUBGROUP_SLICES.items():
        column = X_raw[:, FEATURE_COLUMNS.index(feature)]
        masks_by_slice[slice_name] = [
            (label, np.isfinite(column) & (column >= low) & (column < high)) for low, high, label in bands
        ]
    for slice_name, values in (categorical_slices or {}).items():
        values = np.asarray(values, dtype=str)
        masks_by_slice[slice_name] = [(group, values == group) for group in sorted(set(values) - {""})]
    for slice_name, group_masks in masks_by_slice.items():
        groups = []
        for label, mask in group_masks:
            n = int(mask.sum())
            entry: Dict[str, Any] = {"group": label, "n": n}
            if n >= MIN_SLICE_SAMPLES:
                acc = float(accuracy_score(y_true[mask], y_pred[mask]))
                entry.update({
                    "accuracy": round(acc, 4),
                    "macro_f1": round(float(f1_score(y_true[mask], y_pred[mask], labels=labels, average="macro", zero_division=0)), 4),
                    "accuracy_gap_vs_overall": round(acc - overall, 4),
                })
                worst_gap = max(worst_gap, abs(acc - overall))
            else:
                entry["note"] = "too few samples to evaluate reliably"
            groups.append(entry)
        report["slices"][slice_name] = groups
    report["max_abs_accuracy_gap"] = round(worst_gap, 4)
    report["limitations"] = (
        "Includes dataset-provided slice_* groups." if categorical_slices else
        "Slices use operational features only; add legally permissible slice_* columns "
        "to the dataset for group fairness evaluation."
    )
    return report


def evaluate_quality_gate(crime_metrics: Dict[str, Any], gate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compare holdout metrics with release thresholds; every check is reported."""
    if gate is None:
        from app.config import settings
        gate = settings.model_quality_gate.as_dict()
    calibration = crime_metrics.get("calibration") or {}
    ece = calibration.get("expected_calibration_error")
    checks = [
        ("macro_f1", crime_metrics.get("macro_f1", 0.0), ">=", gate["min_macro_f1"]),
        ("balanced_accuracy", crime_metrics.get("balanced_accuracy", 0.0), ">=", gate["min_balanced_accuracy"]),
        ("zero_recall_classes", len(crime_metrics.get("zero_recall_classes", [])), "<=", gate["max_zero_recall_classes"]),
        ("test_samples", crime_metrics.get("test_samples", 0), ">=", gate["min_test_samples"]),
        ("expected_calibration_error", ece if ece is not None else 1.0, "<=", gate["max_expected_calibration_error"]),
    ]
    results = []
    for name, observed, op, threshold in checks:
        passed = observed >= threshold if op == ">=" else observed <= threshold
        results.append({"check": name, "observed": observed, "operator": op, "threshold": threshold, "passed": bool(passed)})
    if gate.get("require_beats_majority_baseline", True):
        beats = bool(crime_metrics.get("beats_majority_baseline"))
        results.append({"check": "beats_majority_baseline", "observed": beats,
                        "operator": "==", "threshold": True, "passed": beats})
    return {"passed": all(item["passed"] for item in results), "checks": results, "thresholds": gate,
            "evaluated_at": datetime.now(timezone.utc).isoformat()}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dataset_sha256(path: Path = DATASET_PATH) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_float(value: str, column: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DatasetValidationError(
            f"Dataset row {row_number}: '{column}' must be numeric"
        ) from exc
    if not np.isfinite(number):
        raise DatasetValidationError(f"Dataset row {row_number}: '{column}' must be finite")
    return number


def _parse_incident_date(value: str, row_number: int) -> float:
    """Return a sortable UTC timestamp; naive values are taken as UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetValidationError(
            f"Dataset row {row_number}: '{DATE_COLUMN}' must be an ISO 8601 date/time"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def load_training_dataset(
    path: Optional[Path] = None, *, with_context: bool = False, verify_manifest: bool = True,
) -> Tuple[Any, ...]:
    """Load and validate the versioned CSV training dataset (default: DATASET_PATH).

    Returns ``(X, y_crime, y_gang, metadata)``; with ``with_context=True`` a fifth
    item holds the non-feature columns: ``{"incident_dates": array|None,
    "slices": {name: array}}``. ``verify_manifest=False`` skips the manifest hash
    check (used when building a new manifest for this file).
    """
    path = Path(path) if path is not None else DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Training dataset not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected_columns = FEATURE_COLUMNS + TARGET_COLUMNS
        fieldnames = list(reader.fieldnames or [])
        extra_columns = fieldnames[len(expected_columns):]
        bad_extra = [name for name in extra_columns if name not in (DATE_COLUMN, OUTCOME_COLUMN) and not (
            name.startswith(SLICE_PREFIX) and len(name) > len(SLICE_PREFIX))]
        if (fieldnames[:len(expected_columns)] != expected_columns or bad_extra
                or len(set(fieldnames)) != len(fieldnames)):
            raise DatasetValidationError(
                f"Dataset columns do not match schema. Expected {expected_columns} optionally followed by "
                f"'{DATE_COLUMN}', '{OUTCOME_COLUMN}' and '{SLICE_PREFIX}*' columns, got {reader.fieldnames}"
            )
        has_dates = DATE_COLUMN in extra_columns
        has_outcome = OUTCOME_COLUMN in extra_columns
        outcomes: List[int] = []
        slice_columns = [name for name in extra_columns if name.startswith(SLICE_PREFIX)]

        rows: List[List[float]] = []
        crime_labels: List[str] = []
        gang_labels: List[str] = []
        incident_dates: List[float] = []
        slice_values: Dict[str, List[str]] = {name[len(SLICE_PREFIX):]: [] for name in slice_columns}
        missing_counts = {column: 0 for column in expected_columns}

        for row_number, row in enumerate(reader, start=2):
            if all((row.get(column) or "").strip() == "" for column in expected_columns):
                continue
            features = []
            for column in FEATURE_COLUMNS:
                raw = (row.get(column) or "").strip()
                if raw == "":
                    missing_counts[column] += 1
                    features.append(np.nan)
                else:
                    features.append(_parse_float(raw, column, row_number))

            crime = (row.get("crime_type") or "").strip()
            gang = (row.get("gang_label") or "").strip()
            if not crime:
                missing_counts["crime_type"] += 1
            if not gang:
                missing_counts["gang_label"] += 1
            crime_labels.append(crime)
            gang_labels.append(gang)
            rows.append(features)
            if has_dates:
                raw_date = (row.get(DATE_COLUMN) or "").strip()
                if not raw_date:
                    raise DatasetValidationError(
                        f"Dataset row {row_number}: '{DATE_COLUMN}' is required when the column is present"
                    )
                incident_dates.append(_parse_incident_date(raw_date, row_number))
            for name in slice_columns:
                slice_values[name[len(SLICE_PREFIX):]].append((row.get(name) or "").strip())
            if has_outcome:
                raw_outcome = (row.get(OUTCOME_COLUMN) or "").strip()
                if raw_outcome not in ("0", "1"):
                    raise DatasetValidationError(
                        f"Dataset row {row_number}: '{OUTCOME_COLUMN}' must be 0 or 1 when the column is present"
                    )
                outcomes.append(int(raw_outcome))

    if not rows:
        raise DatasetValidationError("Training dataset is empty")

    X = np.asarray(rows, dtype=float)
    y_crime = np.asarray(crime_labels, dtype=str)
    y_gang = np.asarray(gang_labels, dtype=str)

    unknown_crimes = sorted(set(y_crime) - EXPECTED_CRIMES)
    unknown_gangs = sorted(set(y_gang) - EXPECTED_GANGS)
    if unknown_crimes:
        raise DatasetValidationError(f"Unknown crime classes: {unknown_crimes}")
    if unknown_gangs:
        raise DatasetValidationError(f"Unknown gang classes: {unknown_gangs}")
    if "" in y_crime or "" in y_gang:
        raise DatasetValidationError("Target labels cannot be missing")

    for index, column in enumerate(FEATURE_COLUMNS):
        low, high = NUMERIC_RANGES[column]
        observed = X[:, index]
        finite = observed[np.isfinite(observed)]
        if finite.size and (finite.min() < low or finite.max() > high):
            raise DatasetValidationError(
                f"Column '{column}' contains values outside [{low}, {high}]"
            )

    if len(rows) < 100:
        raise DatasetValidationError("Training dataset must contain at least 100 rows")

    manifest: Dict[str, Any] = {}
    if verify_manifest and MANIFEST_PATH.exists() and path.resolve() == DATASET_PATH.resolve():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetValidationError("dataset_manifest.json is not valid JSON") from exc
        expected_hash = manifest.get("sha256")
        actual_hash = _dataset_sha256(path)
        if expected_hash and expected_hash != actual_hash:
            raise DatasetValidationError("Dataset SHA-256 does not match dataset_manifest.json")

    metadata = {
        "rows": int(X.shape[0]),
        "features": FEATURE_COLUMNS.copy(),
        "target_columns": TARGET_COLUMNS.copy(),
        "missing_counts": missing_counts,
        "crime_class_counts": {label: int(np.sum(y_crime == label)) for label in sorted(set(y_crime))},
        "gang_class_counts": {label: int(np.sum(y_gang == label)) for label in sorted(set(y_gang))},
        "dataset_version": manifest.get("dataset_version", DATASET_VERSION),
        "dataset_type": manifest.get("dataset_type", "unknown"),
        "sha256": _dataset_sha256(path),
        "has_incident_dates": has_dates,
        "slice_columns": sorted(slice_values),
        "has_outcome": has_outcome,
    }
    if has_outcome:
        metadata["outcome_rate"] = round(float(np.mean(outcomes)), 4)
    if has_dates:
        metadata["incident_date_range"] = [
            datetime.fromtimestamp(min(incident_dates), timezone.utc).isoformat(),
            datetime.fromtimestamp(max(incident_dates), timezone.utc).isoformat(),
        ]
    if not with_context:
        return X, y_crime, y_gang, metadata
    context = {
        "incident_dates": np.asarray(incident_dates, dtype=float) if has_dates else None,
        "slices": {name: np.asarray(values, dtype=str) for name, values in slice_values.items()},
        "outcome": np.asarray(outcomes, dtype=int) if has_outcome else None,
    }
    return X, y_crime, y_gang, metadata, context


def holdout_split(y_encoded: np.ndarray, incident_dates: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, str]:
    """Return (train_idx, test_idx, kind) for the locked evaluation holdout.

    With incident dates the newest TEST_SIZE fraction of cases is held out
    (ties broken by row order), matching real use: trained on the past, applied
    to new cases. Otherwise a stratified random split is used.
    """
    if incident_dates is not None:
        order = np.argsort(np.asarray(incident_dates, dtype=float), kind="stable")
        n_test = int(np.ceil(len(order) * TEST_SIZE))
        return np.sort(order[:-n_test]), np.sort(order[-n_test:]), "time"
    train_idx, test_idx = train_test_split(
        np.arange(len(y_encoded)), test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y_encoded
    )
    return train_idx, test_idx, "stratified"


def crime_estimator() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=150, max_depth=10, random_state=RANDOM_SEED, class_weight="balanced")


def risk_estimator() -> SklearnPipeline:
    """Danger-score model: logistic regression on the shared features.

    Chosen over a forest because its probabilities are naturally well
    calibrated and each person's score splits exactly into per-feature
    contributions (coefficient x standardised value), which the UI shows.
    """
    return SklearnPipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=2000, C=1.0)),
    ])


RISK_LEVEL_BANDS = (("low", 0, 35), ("medium", 35, 55), ("high", 55, 75), ("critical", 75, 101))


def risk_model_metrics(y_true: np.ndarray, proba: np.ndarray, training_samples: int) -> Dict[str, Any]:
    """Holdout evaluation of the danger-score model.

    ``level_outcome_rates`` is the observed outcome rate inside each risk level:
    for a trustworthy score it rises steeply from low to critical.
    """
    y_true = np.asarray(y_true, dtype=int)
    proba = np.asarray(proba, dtype=float)
    scores = np.clip(1.0 + 99.0 * proba, 1.0, 100.0)
    levels = {}
    for name, low, high in RISK_LEVEL_BANDS:
        mask = (scores >= low) & (scores < high)
        levels[name] = {"samples": int(mask.sum()),
                        "observed_rate": round(float(y_true[mask].mean()), 4) if mask.any() else None}
    both_classes = len(np.unique(y_true)) == 2
    return {
        "target": OUTCOME_COLUMN,
        "training_samples": int(training_samples),
        "test_samples": int(len(y_true)),
        "base_rate": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 4) if both_classes else None,
        "brier_score": round(float(brier_score_loss(y_true, proba)), 4),
        "accuracy_at_0_5": round(float(np.mean((proba >= 0.5) == y_true)), 4),
        "calibration": expected_calibration_error(y_true, np.column_stack([1.0 - proba, proba])),
        "level_outcome_rates": levels,
    }


def calibration_method() -> str:
    if CALIBRATION_METHOD not in CALIBRATION_METHODS:
        raise ValueError(f"AI_CRMS_CALIBRATION must be one of {CALIBRATION_METHODS}, got {CALIBRATION_METHOD!r}")
    return CALIBRATION_METHOD


class CRMSMLPipeline:
    def __init__(self):
        self.crime_classifier = None
        self.gang_predictor = None
        self.label_encoder_crime = LabelEncoder()
        self.label_encoder_gang = LabelEncoder()
        self.imputer: Optional[SimpleImputer] = None
        self.scaler = StandardScaler()
        self.crime_calibrator: Optional[CalibratedClassifierCV] = None
        self.risk_model: Optional[SklearnPipeline] = None
        self.model_version = "v1.0"
        self.is_trained = False
        self.training_metadata: Dict[str, Any] = {}
        self.integrity: Dict[str, Any] = {"status": "unknown", "verified": False}
        self._load_or_train()

    def _imputes_missing(self) -> bool:
        """True when the loaded models were trained with median imputers, so
        unrecorded inputs should reach them as NaN, exactly as in training."""
        return self.imputer is not None and getattr(self, "gang_imputer", None) is not None

    def _transform_features(self, X: np.ndarray) -> np.ndarray:
        X_array = np.asarray(X, dtype=float)
        if self.imputer is not None:
            X_array = self.imputer.transform(X_array)
        return self.scaler.transform(X_array)

    def train(
        self,
        X: Optional[np.ndarray] = None,
        y_crime: Optional[Sequence[str]] = None,
        y_gang: Optional[Sequence[str]] = None,
        *,
        save: bool = True,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Train and rigorously evaluate both classifiers on a deterministic holdout.

        The holdout metrics are the authoritative persisted evaluation metrics.
        When the dataset has incident dates the holdout is the newest cases;
        otherwise it is a stratified random split. Cross-validation on the full
        dataset is additionally reported as a robustness diagnostic.
        ``context`` carries non-feature columns for externally supplied X
        (see ``load_training_dataset(with_context=True)``).
        """
        calibration = calibration_method()
        if X is None:
            X, y_crime, y_gang, dataset_meta, context = load_training_dataset(with_context=True)
        else:
            if y_crime is None or y_gang is None:
                raise ValueError("X, y_crime and y_gang must be supplied together")
            X = np.asarray(X, dtype=float)
            y_crime = np.asarray(y_crime, dtype=str)
            y_gang = np.asarray(y_gang, dtype=str)
            dataset_meta = {
                "rows": int(len(X)), "features": FEATURE_COLUMNS.copy(),
                "target_columns": TARGET_COLUMNS.copy(), "dataset_version": "external",
                "dataset_type": "external", "sha256": None,
            }

        if X.ndim != 2 or X.shape[1] != len(FEATURE_COLUMNS):
            raise DatasetValidationError(
                f"Expected X with {len(FEATURE_COLUMNS)} features; got shape {X.shape}"
            )
        if len(X) != len(y_crime) or len(X) != len(y_gang):
            raise DatasetValidationError("Feature and target row counts must match")
        if len(X) < 100:
            raise DatasetValidationError("Training dataset must contain at least 100 rows")

        y_crime = np.asarray(y_crime, dtype=str)
        y_gang = np.asarray(y_gang, dtype=str)
        self.label_encoder_crime = LabelEncoder().fit(y_crime)
        self.label_encoder_gang = LabelEncoder().fit(y_gang)
        y_crime_enc = self.label_encoder_crime.transform(y_crime)
        y_gang_enc = self.label_encoder_gang.transform(y_gang)

        context = context or {}
        incident_dates = context.get("incident_dates")
        slices = context.get("slices") or {}
        if incident_dates is not None and len(incident_dates) != len(X):
            raise DatasetValidationError("incident_dates must have one value per row")
        crime_train_idx, crime_test_idx, split_kind = holdout_split(y_crime_enc, incident_dates)
        gang_train_idx, gang_test_idx, _ = holdout_split(y_gang_enc, incident_dates)
        time_ordered = split_kind == "time"

        # Fit preprocessing only on each training split. This prevents test-set leakage.
        self.imputer = SimpleImputer(strategy="median")
        X_crime_train = self.imputer.fit_transform(X[crime_train_idx])
        X_crime_test = self.imputer.transform(X[crime_test_idx])
        self.scaler = StandardScaler()
        X_crime_train_scaled = self.scaler.fit_transform(X_crime_train)
        X_crime_test_scaled = self.scaler.transform(X_crime_test)

        y_crime_train = y_crime_enc[crime_train_idx]
        y_crime_test = y_crime_enc[crime_test_idx]
        self.crime_classifier = crime_estimator()
        self.crime_classifier.fit(X_crime_train_scaled, y_crime_train)
        raw_test_proba = self.crime_classifier.predict_proba(X_crime_test_scaled)
        # The calibrator (if any) is what serves predictions, so it is also what
        # the holdout metrics and quality gate measure. The plain forest is kept
        # for its global feature importances.
        self.crime_calibrator = None
        calibration_note = None
        if calibration != "none":
            min_train_class = int(np.bincount(y_crime_train, minlength=len(self.label_encoder_crime.classes_)).min())
            if min_train_class >= CALIBRATION_CV:
                self.crime_calibrator = CalibratedClassifierCV(
                    crime_estimator(), method=calibration, cv=CALIBRATION_CV
                ).fit(X_crime_train_scaled, y_crime_train)
            else:
                calibration_note = (f"Calibration skipped: every class needs at least {CALIBRATION_CV} "
                                    f"training rows (smallest has {min_train_class}).")
        if self.crime_calibrator is not None:
            test_proba = self.crime_calibrator.predict_proba(X_crime_test_scaled)
        else:
            test_proba = raw_test_proba
        crime_pred = test_proba.argmax(axis=1)
        crime_metrics = self._metrics(
            y_crime_test, crime_pred, len(crime_train_idx), len(crime_test_idx),
            self.label_encoder_crime.classes_
        )
        crime_metrics["calibration"] = expected_calibration_error(y_crime_test, test_proba)
        crime_metrics["calibration"]["method"] = calibration if self.crime_calibrator is not None else "none"
        if self.crime_calibrator is not None:
            crime_metrics["calibration"]["uncalibrated_expected_calibration_error"] = (
                expected_calibration_error(y_crime_test, raw_test_proba)["expected_calibration_error"]
            )
        if calibration_note:
            crime_metrics["calibration"]["note"] = calibration_note
        crime_metrics["subgroup_evaluation"] = subgroup_evaluation(
            X[crime_test_idx], y_crime_test, crime_pred, self.label_encoder_crime.classes_,
            categorical_slices={name: values[crime_test_idx] for name, values in slices.items()},
        )
        crime_cv = self._cross_validation(
            X, y_crime_enc, self.label_encoder_crime.classes_, crime_estimator(),
            order=np.argsort(incident_dates, kind="stable") if time_ordered else None,
        )
        crime_metrics["cross_validation"] = crime_cv

        # Gang preprocessing is evaluated independently because its stratified split
        # can differ from the crime target split. Persist the crime preprocessing
        # above because prediction uses the crime model's feature transformation.
        # Exclude is_gang_member from the gang classifier: in this dataset and
        # schema it directly reveals whether the gang_label target is "None".
        X_gang = X[:, GANG_FEATURE_INDICES]
        gang_imputer = SimpleImputer(strategy="median")
        X_gang_train = gang_imputer.fit_transform(X_gang[gang_train_idx])
        X_gang_test = gang_imputer.transform(X_gang[gang_test_idx])
        gang_scaler = StandardScaler()
        X_gang_train_scaled = gang_scaler.fit_transform(X_gang_train)
        X_gang_test_scaled = gang_scaler.transform(X_gang_test)
        self.gang_predictor = RandomForestClassifier(
            n_estimators=100, max_depth=8, random_state=RANDOM_SEED, class_weight="balanced"
        )
        self.gang_predictor.fit(X_gang_train_scaled, y_gang_enc[gang_train_idx])
        gang_pred = self.gang_predictor.predict(X_gang_test_scaled)
        gang_metrics = self._metrics(
            y_gang_enc[gang_test_idx], gang_pred, len(gang_train_idx), len(gang_test_idx),
            self.label_encoder_gang.classes_
        )
        gang_metrics["calibration"] = expected_calibration_error(
            y_gang_enc[gang_test_idx], self.gang_predictor.predict_proba(X_gang_test_scaled)
        )
        gang_metrics["cross_validation"] = self._cross_validation(
            X_gang, y_gang_enc, self.label_encoder_gang.classes_,
            RandomForestClassifier(n_estimators=100, max_depth=8, random_state=RANDOM_SEED, class_weight="balanced"),
            order=np.argsort(incident_dates, kind="stable") if time_ordered else None,
        )

        # Persist the crime preprocessing used by the prediction API. The gang model
        # has the same raw feature schema and deterministic preprocessing, but its
        # fitted transformer is retained separately for correct gang predictions.
        self.gang_imputer = gang_imputer
        self.gang_scaler = gang_scaler

        # Learned danger score, when the dataset carries an observed outcome.
        # Same holdout rows as the crime model, so it is judged on unseen cases.
        self.risk_model = None
        risk_metrics = None
        outcome = context.get("outcome")
        if outcome is not None:
            outcome = np.asarray(outcome, dtype=int)
            if len(outcome) != len(X):
                raise DatasetValidationError(f"{OUTCOME_COLUMN} must have one value per row")
            if len(np.unique(outcome[crime_train_idx])) == 2:
                self.risk_model = risk_estimator().fit(X[crime_train_idx], outcome[crime_train_idx])
                risk_metrics = risk_model_metrics(
                    outcome[crime_test_idx], self.risk_model.predict_proba(X[crime_test_idx])[:, 1],
                    len(crime_train_idx),
                )

        feature_importances = {
            feature: round(float(value), 8)
            for feature, value in zip(FEATURE_COLUMNS, self.crime_classifier.feature_importances_)
        }

        dataset_hash = dataset_meta.get("sha256") or "external"
        self.model_version = f"v{PIPELINE_VERSION}-{dataset_hash[:8]}" if dataset_hash != "external" else f"v{PIPELINE_VERSION}-external"
        trained_at = _utc_now().isoformat()
        self.training_metadata = {
            "pipeline_version": PIPELINE_VERSION,
            "model_version": self.model_version,
            "dataset": dataset_meta,
            "random_seed": RANDOM_SEED,
            "test_size": TEST_SIZE,
            "evaluation_method": (
                "time-based holdout (newest 20% of cases) + forward-chaining time-series cross-validation"
                if time_ordered else "stratified 80/20 holdout + 5-fold stratified cross-validation"
            ),
            "holdout_split": split_kind,
            "calibration_method": crime_metrics["calibration"]["method"],
            "cv_folds": CV_FOLDS,
            "feature_columns": FEATURE_COLUMNS.copy(),
            "model_feature_columns": {
                "crime_classifier": FEATURE_COLUMNS.copy(),
                "gang_predictor": GANG_FEATURE_COLUMNS.copy(),
            },
            "crime_classes": self.label_encoder_crime.classes_.tolist(),
            "gang_classes": self.label_encoder_gang.classes_.tolist(),
            "crime_classifier": crime_metrics,
            "gang_predictor": gang_metrics,
            "feature_importances": feature_importances,
            "risk_score_config": RISK_SCORE_CONFIG,
            "risk_score_method": "learned_logistic_regression" if self.risk_model is not None else "fixed_weight_prototype",
            "risk_model": risk_metrics,
            "risk_level_thresholds": {"medium": 35, "high": 55, "critical": 75},
            "risk_score_disclaimer": "Prototype decision-support score; not clinically or legally validated.",
            "quality_gate": evaluate_quality_gate(crime_metrics),
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "trained_at": trained_at,
        }
        self.is_trained = True
        if save:
            self._save_models()
        return {
            "crime_classifier": crime_metrics,
            "gang_predictor": gang_metrics,
            "feature_importances": feature_importances,
            "model_version": self.model_version,
            "trained_at": trained_at,
            "dataset": dataset_meta,
            "evaluation_method": self.training_metadata["evaluation_method"],
            "quality_gate": self.training_metadata["quality_gate"],
            "risk_model": risk_metrics,
        }

    @staticmethod
    def _metrics(
        y_true: np.ndarray, y_pred: np.ndarray, training_samples: int, test_samples: int, classes: Sequence[str]
    ) -> Dict[str, Any]:
        labels = np.arange(len(classes))
        cm = confusion_matrix(y_true, y_pred, labels=labels)
        per_class = {}
        p, r, f, support = precision_score(
            y_true, y_pred, labels=labels, average=None, zero_division=0
        ), recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0), f1_score(
            y_true, y_pred, labels=labels, average=None, zero_division=0
        ), np.bincount(y_true, minlength=len(labels))
        predicted_support = np.bincount(np.asarray(y_pred, dtype=int), minlength=len(labels))
        for idx, label in enumerate(classes):
            per_class[str(label)] = {
                "precision": float(p[idx]),
                "recall": float(r[idx]),
                "f1": float(f[idx]),
                "support": int(support[idx]),
                "predicted_count": int(predicted_support[idx]),
            }
        majority_baseline = float(support.max() / max(int(support.sum()), 1))
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
            "macro_precision": float(precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
            "macro_recall": float(recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
            "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
            "majority_baseline_accuracy": majority_baseline,
            "beats_majority_baseline": bool(accuracy_score(y_true, y_pred) > majority_baseline),
            "zero_recall_classes": [str(classes[idx]) for idx in range(len(classes)) if support[idx] > 0 and r[idx] == 0],
            "training_samples": int(training_samples),
            "test_samples": int(test_samples),
            "class_distribution": {str(label): int(support[idx]) for idx, label in enumerate(classes)},
            "predicted_class_distribution": {str(label): int(predicted_support[idx]) for idx, label in enumerate(classes)},
            "per_class": per_class,
            "confusion_matrix": cm.astype(int).tolist(),
            "classes": [str(c) for c in classes],
        }

    @staticmethod
    def _cross_validation(
        X: np.ndarray, y: np.ndarray, classes: Sequence[str], estimator: RandomForestClassifier,
        order: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Robustness diagnostic. With ``order`` (chronological row order) folds
        always train on earlier cases and test on later ones."""
        pipeline = SklearnPipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ])
        if order is not None:
            X, y = X[order], y[order]
            folds = CV_FOLDS
            cv = TimeSeriesSplit(n_splits=folds)
        else:
            min_class_count = min(np.bincount(y))
            folds = min(CV_FOLDS, int(min_class_count))
            if folds < 2:
                return {"enabled": False, "reason": "At least two samples per class are required."}
            cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_SEED)
        scores = cross_validate(
            pipeline, X, y, cv=cv,
            scoring={
                "accuracy": "accuracy",
                "precision": make_scorer(precision_score, average="weighted", zero_division=0),
                "recall": make_scorer(recall_score, average="weighted", zero_division=0),
                "f1": make_scorer(f1_score, average="weighted", zero_division=0),
            },
            n_jobs=1,
        )
        return {
            "enabled": True,
            "folds": folds,
            "scheme": "time_series" if order is not None else "stratified",
            "accuracy_mean": float(np.mean(scores["test_accuracy"])),
            "accuracy_std": float(np.std(scores["test_accuracy"])),
            "precision_mean": float(np.mean(scores["test_precision"])),
            "recall_mean": float(np.mean(scores["test_recall"])),
            "f1_mean": float(np.mean(scores["test_f1"])),
        }

    def predict(self, criminal_data: Dict) -> Dict:
        if not self.is_trained:
            self._load_or_train()

        self._validate_risk_inputs(criminal_data)
        features = self._extract_features(criminal_data, impute_missing=self._imputes_missing())
        feature_quality = self._feature_input_quality(criminal_data)
        X_scaled = self._transform_features(np.array([features], dtype=float))

        crime_model = self.crime_calibrator if self.crime_calibrator is not None else self.crime_classifier
        crime_proba = crime_model.predict_proba(X_scaled)[0]
        crime_idx = int(np.argmax(crime_proba))
        predicted_crime = self.label_encoder_crime.inverse_transform([crime_idx])[0]
        crime_confidence = float(crime_proba[crime_idx])

        # Older bundled artifacts were trained with is_gang_member included,
        # leaking the gang target. Fail closed for those legacy artifacts instead
        # of emitting a misleading gang prediction until a safe candidate is trained.
        gang_feature_count = getattr(self.gang_predictor, "n_features_in_", None)
        legacy_gang_model = gang_feature_count == len(FEATURE_COLUMNS)
        if legacy_gang_model:
            predicted_gang_label = "None"
            gang_confidence = 0.0
            gang_affiliation_prob = 0.0
            gang_prediction_available = False
        else:
            gang_features = np.asarray([features], dtype=float)[:, GANG_FEATURE_INDICES]
            gang_input = self.gang_imputer.transform(gang_features)
            gang_scaled = self.gang_scaler.transform(gang_input)
            gang_proba = self.gang_predictor.predict_proba(gang_scaled)[0]
            gang_idx = int(np.argmax(gang_proba))
            predicted_gang_label = self.label_encoder_gang.inverse_transform([gang_idx])[0]
            gang_confidence = float(gang_proba[gang_idx])
            gang_prediction_available = True

            is_gang_affiliated = predicted_gang_label != "None"
            if "None" in self.label_encoder_gang.classes_:
                none_idx = int(self.label_encoder_gang.transform(["None"])[0])
                gang_affiliation_prob = (
                    gang_confidence if is_gang_affiliated else 1 - float(gang_proba[none_idx])
                )
            else:
                gang_affiliation_prob = gang_confidence if is_gang_affiliated else 0.0

        if self.risk_model is not None:
            self._validate_risk_inputs(criminal_data)
            risk_score, risk_factors = self._learned_risk_score(features)
        else:
            risk_score, risk_factors = self._calculate_risk_score(criminal_data, crime_confidence, gang_affiliation_prob)
        risk_level = self._risk_level(risk_score)

        overall_confidence = crime_confidence if not gang_prediction_available else (crime_confidence + gang_confidence) / 2
        explanation = self._build_prediction_explanation(
            features=features,
            predicted_crime=predicted_crime,
            crime_confidence=crime_confidence,
            predicted_gang=predicted_gang_label if gang_prediction_available and predicted_gang_label != "None" else None,
            gang_probability=gang_affiliation_prob,
        )
        return {
            "predicted_crime_type": predicted_crime,
            "crime_type_confidence": round(crime_confidence * 100, 1),
            "gang_affiliation_probability": round(gang_affiliation_prob * 100, 1),
            "predicted_gang": predicted_gang_label if gang_prediction_available and predicted_gang_label != "None" else None,
            "gang_prediction_available": gang_prediction_available,
            "gang_prediction_warning": None if gang_prediction_available else "Gang prediction is disabled because the loaded legacy model uses a target-leaking feature. Train and independently validate a candidate before enabling this output.",
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "confidence_overall": round(overall_confidence * 100, 1),
            "input_features": {
                "prior_convictions": criminal_data.get("prior_convictions", 0),
                "crime_type": criminal_data.get("crime_type", "Unknown"),
                "gang_affiliated": criminal_data.get("gang_id") is not None,
                "is_wanted": criminal_data.get("is_wanted", False),
                "violence_history": criminal_data.get("violence_history", 0),
                "is_incarcerated": criminal_data.get("is_incarcerated", False),
                "feature_input_quality": feature_quality,
                "gang_prediction_available": gang_prediction_available,
                "gang_prediction_warning": None if gang_prediction_available else "Gang prediction is disabled because the loaded legacy model uses a target-leaking feature. Train and independently validate a candidate before enabling this output.",
                "model_validity_warning": (
                    "The loaded model is trained on synthetic demonstration data (or data of unknown provenance) "
                    "and has not been validated for real-world use."
                    if self.is_synthetic else None
                ),
                "calibration_warning": self._calibration_warning(),
                "risk_factors": risk_factors,
                "risk_score_method": self._risk_score_method(),
                "explanation": explanation,
            },
        }

    def _calibration_warning(self) -> str:
        ece = ((self.training_metadata.get("crime_classifier") or {}).get("calibration") or {}).get(
            "expected_calibration_error", "unknown")
        if self.crime_calibrator is not None:
            return (f"Confidence values are {self.training_metadata.get('calibration_method', 'calibrated')}-calibrated "
                    f"on training data. Holdout expected calibration error: {ece}. They are still not validated "
                    "real-world probabilities for an individual case.")
        return f"Confidence values are uncalibrated model scores, not probabilities. Holdout expected calibration error: {ece}."

    def _build_prediction_explanation(
        self,
        features: Sequence[float],
        predicted_crime: str,
        crime_confidence: float,
        predicted_gang: Optional[str],
        gang_probability: float,
    ) -> Dict[str, Any]:
        """Expose model-derived feature importance without claiming causality.

        Random Forest ``feature_importances_`` is a global model statistic, not a
        per-record causal explanation. The API therefore labels it explicitly as
        model feature importance and pairs it with the actual evaluated value.
        """
        importances = np.asarray(self.crime_classifier.feature_importances_, dtype=float)
        total = float(importances.sum()) or 1.0
        relative = importances / total
        # Unrecorded inputs are NaN here; report the training median the model
        # actually used in their place, and flag them as imputed.
        medians = getattr(self.imputer, "statistics_", None)
        rows = []
        for index, (name, value, importance) in enumerate(zip(FEATURE_COLUMNS, features, relative)):
            imputed = not np.isfinite(value)
            if imputed:
                value = medians[index] if medians is not None and np.isfinite(medians[index]) else 0.0
            rows.append({
                "feature": name,
                "value": round(float(value), 4),
                "imputed": bool(imputed),
                "relative_importance": round(float(importance), 6),
            })
        rows.sort(key=lambda item: (-item["relative_importance"], item["feature"]))
        top = rows[:5]
        return {
            "type": "random_forest_feature_importance",
            "method": "global_random_forest_feature_importance",
            "model_version": self.model_version,
            "predicted_crime": predicted_crime,
            "crime_confidence": round(crime_confidence * 100, 1),
            "predicted_gang": predicted_gang,
            "gang_probability": round(gang_probability * 100, 1),
            "top_features": top,
            "all_features": rows,
            "interpretation": "Important model features indicate relative model importance; they do not establish that a feature caused the prediction.",
        }

    FEATURE_LABELS = {
        "prior_convictions": "Prior convictions", "age": "Age at incident", "is_gang_member": "Gang membership",
        "weapons_involved": "Weapon involved", "drug_involvement": "Drug involvement",
        "financial_motivation": "Financial motive", "tech_involvement": "Technology used",
        "violence_history": "Violence history", "location_risk": "Location risk",
        "time_of_crime": "Hour of incident", "associates_count": "Known associates",
    }

    def _risk_score_method(self) -> Dict[str, Any]:
        if self.risk_model is not None:
            metrics = self.training_metadata.get("risk_model") or {}
            return {
                "type": "learned_logistic_regression",
                "target": OUTCOME_COLUMN,
                "holdout_roc_auc": metrics.get("roc_auc"),
                "disclaimer": ("Learned from the training data's re-arrest outcome. Its accuracy holds only for "
                               "people like those in that data; not a legal or clinical risk assessment."),
            }
        return {
            "type": "deterministic_weighted_prototype",
            "weights": RISK_SCORE_CONFIG,
            "disclaimer": "Prototype decision-support score; not clinically or legally validated.",
        }

    def _learned_risk_score(self, features: Sequence[float]) -> Tuple[float, List[Dict[str, Any]]]:
        """Score = 1 + 99 x P(re-arrest within two years), with an exact breakdown.

        For logistic regression the log-odds is the intercept plus, per
        feature, coefficient x standardised value, so each factor's
        ``contribution`` is exactly how much it raised or lowered the odds.
        """
        X = np.asarray([features], dtype=float)
        probability = float(self.risk_model.predict_proba(X)[0, 1])
        imputer = self.risk_model.named_steps["imputer"]
        scaler = self.risk_model.named_steps["scaler"]
        model = self.risk_model.named_steps["model"]
        used = imputer.transform(X)
        standardised = scaler.transform(used)[0]
        factors = []
        for index, name in enumerate(FEATURE_COLUMNS):
            coefficient = float(model.coef_[0][index])
            factors.append({
                "name": self.FEATURE_LABELS.get(name, name),
                "key": name,
                "normalized_value": round(float(used[0][index]), 4),
                "imputed": bool(not np.isfinite(X[0][index])),
                "weight": round(coefficient, 4),
                "contribution": round(coefficient * float(standardised[index]), 3),
            })
        factors.sort(key=lambda item: (-abs(item["contribution"]), item["key"]))
        return float(np.clip(1.0 + 99.0 * probability, 1.0, 100.0)), factors

    @staticmethod
    def _risk_level(score: float) -> str:
        """Map the bounded score to stable prototype risk bands."""
        if score >= 75:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 35:
            return "medium"
        return "low"

    @staticmethod
    def _feature_input_quality(data: Dict) -> Dict[str, Any]:
        """Report which model inputs were observed versus defaulted/derived.

        This is a data-completeness warning, not a probability calibration or
        an assessment of the reliability of the underlying record.
        """
        observed = set()
        derived = set()
        if data.get("prior_convictions") is not None:
            observed.add("prior_convictions")
        if data.get("date_of_birth"):
            derived.add("age")
        elif data.get("age") is not None:
            observed.add("age")
        if data.get("is_gang_member") is not None:
            observed.add("is_gang_member")
        elif data.get("gang_id") is not None:
            derived.add("is_gang_member")
        for name in ("weapons_involved", "drug_involvement", "financial_motivation", "tech_involvement", "violence_history", "location_risk", "time_of_crime", "associates_count"):
            if data.get(name) is not None:
                observed.add(name)
        if data.get("known_associates") is not None and "associates_count" not in observed:
            derived.add("associates_count")
        # Only mark time as derived when a caller provides an actual incident timestamp.
        if data.get("incident_date") and "time_of_crime" not in observed:
            derived.add("time_of_crime")
        covered = observed | derived
        missing = [name for name in FEATURE_COLUMNS if name not in covered]
        return {
            "feature_count": len(FEATURE_COLUMNS),
            "observed_count": len(observed),
            "derived_count": len(derived),
            "missing_count": len(missing),
            "coverage_percent": round(100.0 * len(covered) / len(FEATURE_COLUMNS), 1),
            "observed_features": [name for name in FEATURE_COLUMNS if name in observed],
            "derived_features": [name for name in FEATURE_COLUMNS if name in derived],
            "defaulted_features": missing,
            "warning": "Low input coverage means predictions may be unreliable. Confidence values are model scores, not validated real-world probabilities." if len(covered) < len(FEATURE_COLUMNS) else None,
        }

    @staticmethod
    def _extract_features(data: Dict, impute_missing: bool = False) -> List[float]:
        """Build inference features only from observed inputs, never from the target.

        The previous implementation inferred weapons/drug/financial/technology
        features from ``crime_type``. Since crime_type is the prediction target in
        the crime classifier, that created target leakage and made inference depend
        on the answer it was supposed to predict.

        Unrecorded fields use documented, conservative defaults. With
        ``impute_missing=True`` they are NaN instead, so a model trained with a
        median imputer sees unrecorded inputs exactly as it did in training
        (blank CSV cells), rather than a default that reads as an explicit "no".
        The training-data exporter uses the same mode, so its rows match inference.
        """
        missing = np.nan if impute_missing else None
        age: float = 30 if missing is None else missing
        if data.get("date_of_birth"):
            try:
                dob_value = data["date_of_birth"]
                dob = (datetime.fromisoformat(dob_value.replace("Z", "+00:00"))
                       if isinstance(dob_value, str) else dob_value)
                # Age at the incident when its date is known, so training rows
                # (historical incidents) and live predictions measure the same thing.
                as_of = RISK_REFERENCE_DATE
                incident = data.get("incident_date")
                if incident:
                    as_of = (datetime.fromisoformat(incident.replace("Z", "+00:00"))
                             if isinstance(incident, str) else incident).date()
                age = (as_of - dob.replace(tzinfo=None).date()).days // 365
            except (TypeError, ValueError, AttributeError):
                pass
        elif data.get("age") is not None:
            try:
                age = int(data["age"])
            except (TypeError, ValueError):
                raise ValueError("age must be numeric") from None
            if age < 16 or age > 100:
                raise ValueError("age must be between 16 and 100")

        def numeric(name: str, default: float, low: float, high: float) -> float:
            raw = data.get(name)
            if raw in (None, ""):
                return default
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not np.isfinite(value) or value < low or value > high:
                raise ValueError(f"{name} must be between {low} and {high}")
            return value

        def fallback(value: float) -> float:
            return value if missing is None else missing

        prior = numeric("prior_convictions", fallback(0.0), 0.0, 100.0)
        if "is_gang_member" in data or "gang_id" in data or missing is None:
            gang_member = data.get("is_gang_member", bool(data.get("gang_id")))
            if not isinstance(gang_member, (bool, np.bool_, int, np.integer, float, np.floating)) or gang_member not in (0, 1, False, True):
                raise ValueError("is_gang_member must be boolean or 0/1")
            gang_feature = float(bool(gang_member))
        else:
            gang_feature = missing  # no offender record: membership is unknown, not "no"
        if data.get("known_associates") is not None or missing is None:
            associates_default = float(min(len([x for x in (data.get("known_associates") or "").split(",") if x.strip()]), 15))
        else:
            associates_default = missing
        incident_hour = CRMSMLPipeline._incident_hour(data, default=-1)
        hour_default = float(incident_hour) if incident_hour >= 0 else fallback(12.0)
        return [
            prior,
            float(max(16, min(70, age))) if np.isfinite(age) else age,
            gang_feature,
            numeric("weapons_involved", fallback(0.0), 0.0, 1.0),
            numeric("drug_involvement", fallback(0.0), 0.0, 1.0),
            numeric("financial_motivation", fallback(0.0), 0.0, 1.0),
            numeric("tech_involvement", fallback(0.0), 0.0, 1.0),
            numeric("violence_history", fallback(0.0), 0.0, 100.0),
            numeric("location_risk", fallback(0.3), 0.0, 1.0),
            numeric("time_of_crime", hour_default, 0.0, 23.0),
            numeric("associates_count", associates_default, 0.0, 1000.0),
        ]

    @staticmethod
    def _incident_hour(data: Dict, default: int = 12) -> int:
        """Use a recorded incident timestamp if available; never infer from crime type."""
        raw = data.get("incident_date")
        if not raw:
            return default
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00")) if isinstance(raw, str) else raw
            return int(value.hour)
        except (TypeError, ValueError, AttributeError):
            return default

    def _validate_risk_inputs(self, data: Dict) -> None:
        """Validate values used by the deterministic prototype risk score."""
        prior = data.get("prior_convictions", 0)
        violence = data.get("violence_history", 0)
        for name, value in (("prior_convictions", prior), ("violence_history", violence)):
            try:
                numeric = float(value or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not np.isfinite(numeric) or numeric < 0:
                raise ValueError(f"{name} must be a finite non-negative number")

        for name in ("is_wanted", "is_incarcerated"):
            value = data.get(name, False)
            if value is not None and not isinstance(value, (bool, np.bool_)):
                raise ValueError(f"{name} must be boolean")

        crime_type = data.get("crime_type")
        if crime_type is not None and crime_type not in EXPECTED_CRIMES:
            raise ValueError(f"Unsupported crime_type: {crime_type}")

    def _calculate_risk_score(self, data: Dict, crime_conf: float, gang_prob: float) -> Tuple[float, List[Dict[str, Any]]]:
        """Calculate a transparent 1-100 prototype decision-support score.

        Each factor is normalized to [0, 1], multiplied by an explicit weight,
        and recorded so the UI/API can explain the resulting score. This is not
        a clinically or legally validated risk assessment.
        """
        self._validate_risk_inputs(data)
        crime_conf = float(np.clip(crime_conf, 0.0, 1.0))
        gang_prob = float(np.clip(gang_prob, 0.0, 1.0))
        prior = float(data.get("prior_convictions", 0) or 0)
        violence = float(data.get("violence_history", 0) or 0)
        wanted = bool(data.get("is_wanted", False))
        incarcerated = bool(data.get("is_incarcerated", False))
        crime_type = data.get("crime_type") or ""

        normalized = {
            "prior_convictions": min(prior / RISK_SCORE_CONFIG["prior_convictions"]["max_value"], 1.0),
            "violence_history": min(violence / RISK_SCORE_CONFIG["violence_history"]["max_value"], 1.0),
            "gang_probability": gang_prob,
            "crime_confidence": crime_conf,
            "wanted_status": 1.0 if wanted else 0.0,
            "crime_severity": CRIME_SEVERITY.get(crime_type, 0.0),
        }

        factors = []
        score = 1.0
        labels = {
            "prior_convictions": "Prior convictions",
            "violence_history": "Violence history",
            "gang_probability": "Gang affiliation probability",
            "crime_confidence": "Crime classification confidence",
            "wanted_status": "Wanted status",
            "crime_severity": "Crime severity category",
        }
        for key in ("prior_convictions", "violence_history", "gang_probability", "crime_confidence", "wanted_status", "crime_severity"):
            weight = RISK_SCORE_CONFIG[key]["weight"]
            contribution = normalized[key] * weight
            score += contribution
            factors.append({
                "name": labels[key],
                "key": key,
                "normalized_value": round(normalized[key], 4),
                "weight": weight,
                "contribution": round(contribution, 2),
            })

        if incarcerated:
            adjustment = RISK_SCORE_CONFIG["incarcerated_adjustment"]["weight"]
            score += adjustment
            factors.append({
                "name": "Incarceration status adjustment",
                "key": "incarcerated_adjustment",
                "normalized_value": 1.0,
                "weight": adjustment,
                "contribution": adjustment,
            })

        score = float(np.clip(score, 1.0, 100.0))
        factors.sort(key=lambda item: (-abs(item["contribution"]), item["key"]))
        return score, factors

    def find_similar_criminals(self, criminal_data: Dict, all_criminals: List[Dict], top_k: int = 5) -> List[Dict]:
        """Return top-K similar records using the model's engineered feature space.

        This is feature-vector retrieval, not an embedding model. Raw engineered
        features are transformed with the same imputer/scaler used by the crime
        classifier before cosine similarity is calculated. Invalid records are
        skipped rather than breaking the prediction endpoint.
        """
        if not all_criminals:
            return []
        try:
            limit = max(0, min(int(top_k), 50))
        except (TypeError, ValueError):
            limit = 5
        if limit == 0:
            return []

        try:
            target_raw = np.asarray(self._extract_features(criminal_data, impute_missing=self._imputes_missing()), dtype=float).reshape(1, -1)
            target_vector = self._transform_features(target_raw)[0]
        except (TypeError, ValueError, OverflowError):
            return []
        results = []
        for criminal in all_criminals:
            # Never return the subject itself, even when the caller supplied a
            # duplicate object or the feature vectors are identical.
            if criminal.get("id") is not None and criminal.get("id") == criminal_data.get("id"):
                continue
            try:
                candidate_raw = np.asarray(self._extract_features(criminal, impute_missing=self._imputes_missing()), dtype=float).reshape(1, -1)
                candidate_vector = self._transform_features(candidate_raw)[0]
                similarity = self._cosine_similarity(target_vector, candidate_vector)
                matching_features = self._matching_features(target_raw[0], candidate_raw[0])
            except (TypeError, ValueError, OverflowError):
                continue
            similarity_score = round(float(np.clip(similarity, 0.0, 1.0)) * 100, 1)
            record_id = criminal.get("id")
            record_name = f"{criminal.get('first_name', '')} {criminal.get('last_name', '')}".strip() or f"Record #{record_id if record_id is not None else 'unknown'}"
            results.append({
                # Canonical API names.
                "similar_record_id": record_id,
                "name": record_name,
                "similarity_score": similarity_score,
                "matching_features": matching_features,
                # Backward-compatible aliases retained for existing UI consumers.
                "id": record_id,
                "score": similarity_score,
                "crime_type": criminal.get("crime_type"),
            })
        results.sort(key=lambda item: (-item["score"], item["id"] if item["id"] is not None else float("inf")))
        return results[:limit]

    @staticmethod
    def _matching_features(a: np.ndarray, b: np.ndarray) -> List[str]:
        """Return feature names whose engineered values are close enough to match."""
        matches = []
        for name, left, right in zip(FEATURE_COLUMNS, a, b):
            scale = max(abs(float(left)), abs(float(right)), 1.0)
            if abs(float(left) - float(right)) / scale <= 0.10:
                matches.append(name)
        return matches

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if not np.isfinite(norm_a) or not np.isfinite(norm_b) or norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.clip(np.dot(a, b) / (norm_a * norm_b), -1.0, 1.0))

    def _save_models(self, output_dir: Optional[Path] = None) -> None:
        """Persist this instance's artifacts to a chosen directory.

        The default remains the active artifact directory for compatibility.
        Candidate training always supplies a separate directory so an unreviewed
        model can never overwrite the active model files.
        """
        output_dir = Path(output_dir) if output_dir is not None else MODEL_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, artifact in (
            ("crime_classifier.pkl", self.crime_classifier),
            ("gang_predictor.pkl", self.gang_predictor),
        ):
            with (output_dir / filename).open("wb") as handle:
                pickle.dump(artifact, handle, protocol=pickle.HIGHEST_PROTOCOL)
        with (output_dir / "encoders.pkl").open("wb") as handle:
            pickle.dump({
                "crime": self.label_encoder_crime,
                "gang": self.label_encoder_gang,
                "scaler": self.scaler,
                "imputer": self.imputer,
                "crime_calibrator": self.crime_calibrator,
                "gang_scaler": getattr(self, "gang_scaler", self.scaler),
                "gang_imputer": getattr(self, "gang_imputer", self.imputer),
                "feature_columns": FEATURE_COLUMNS,
                "gang_feature_columns": GANG_FEATURE_COLUMNS,
                "risk_model": getattr(self, "risk_model", None),
            }, handle, protocol=pickle.HIGHEST_PROTOCOL)
        hashes = {name: _file_sha256(output_dir / name) for name in ARTIFACT_FILES}
        self.training_metadata["artifact_sha256"] = hashes
        self.training_metadata["artifact_signature"] = sign_artifact_hashes(hashes, self.model_version)
        (output_dir / "metadata.json").write_text(
            json.dumps(self.training_metadata, indent=2), encoding="utf-8"
        )

    def save_candidate(self) -> str:
        """Persist a trained candidate without touching the active model artifacts."""
        candidate_id = f"{self.model_version}-{uuid.uuid4().hex[:8]}"
        candidate_dir = CANDIDATES_DIR / candidate_id
        self._save_models(candidate_dir)
        return str(candidate_dir.resolve())

    def activate_candidate(self, candidate_dir: Path) -> None:
        """Atomically stage a candidate's files, then reload this pipeline instance."""
        candidate_dir = Path(candidate_dir).resolve()
        candidates_root = CANDIDATES_DIR.resolve()
        if candidates_root not in candidate_dir.parents:
            raise ValueError("Candidate path is outside the model candidates directory")
        required = ["crime_classifier.pkl", "gang_predictor.pkl", "encoders.pkl", "metadata.json"]
        if not candidate_dir.is_dir() or any(not (candidate_dir / name).is_file() for name in required):
            raise ValueError("Candidate model artifacts are incomplete")
        try:
            candidate_metadata = json.loads((candidate_dir / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Candidate metadata is invalid") from exc
        model_feature_columns = candidate_metadata.get("model_feature_columns", {})
        if candidate_metadata.get("pipeline_version") != PIPELINE_VERSION:
            raise ValueError("Candidate pipeline version is incompatible; retrain it using the current pipeline")
        if model_feature_columns.get("crime_classifier") != FEATURE_COLUMNS:
            raise ValueError("Candidate crime feature schema is incompatible")
        if model_feature_columns.get("gang_predictor") != GANG_FEATURE_COLUMNS:
            raise ValueError("Candidate gang feature schema is incompatible or contains a target-leaking feature")
        try:
            verify_artifacts(candidate_dir, candidate_metadata, require_signature=True)
        except ArtifactIntegrityError as exc:
            raise ValueError(str(exc)) from exc

        staging = MODEL_DIR / f".activation-{uuid.uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for name in required:
                shutil.copy2(candidate_dir / name, staging / name)
            # Keep backups so an interrupted promotion can be manually recovered.
            backup = staging / "previous"
            backup.mkdir()
            for name in required:
                active_file = MODEL_DIR / name
                if active_file.exists():
                    shutil.copy2(active_file, backup / name)
            replaced = []
            try:
                for name in required:
                    os.replace(staging / name, MODEL_DIR / name)
                    replaced.append(name)
                self._load_or_train()
            except Exception:
                # Restore the previous active set if promotion or reload fails.
                for name in replaced:
                    old_file = backup / name
                    if old_file.exists():
                        shutil.copy2(old_file, MODEL_DIR / name)
                self._load_or_train()
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _load_or_train(self) -> None:
        metadata: Dict[str, Any] = {}
        if METADATA_PATH.exists():
            try:
                metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {}
        if self._is_stale_demo_model(metadata):
            logger.warning("Active demo model was trained on a different synthetic dataset; retraining on %s.",
                           DATASET_PATH.name)
            self.train()
            self.integrity = {"status": "verified", "verified": True}
            return
        if all((MODEL_DIR / name).exists() for name in ARTIFACT_FILES):
            # Raises ArtifactIntegrityError (never silently retrains) on tampering.
            self.integrity = verify_artifacts(MODEL_DIR, metadata)
            if not self.integrity["verified"]:
                logger.warning("Loading legacy UNSIGNED model artifacts from %s; retrain to sign them.", MODEL_DIR)
        try:
            with (MODEL_DIR / "crime_classifier.pkl").open("rb") as handle:
                self.crime_classifier = pickle.load(handle)
            with (MODEL_DIR / "gang_predictor.pkl").open("rb") as handle:
                self.gang_predictor = pickle.load(handle)
            with (MODEL_DIR / "encoders.pkl").open("rb") as handle:
                enc = pickle.load(handle)
            self.label_encoder_crime = enc["crime"]
            self.label_encoder_gang = enc["gang"]
            self.scaler = enc["scaler"]
            self.imputer = enc.get("imputer")
            self.crime_calibrator = enc.get("crime_calibrator")
            self.gang_scaler = enc.get("gang_scaler", self.scaler)
            self.gang_imputer = enc.get("gang_imputer", self.imputer)
            self.risk_model = enc.get("risk_model")
            if metadata:
                self.training_metadata = metadata
                self.model_version = self.training_metadata.get("model_version", "v1.0")
            else:
                self.training_metadata = {"model_version": "v1.0", "legacy_artifact": True}
                self.model_version = "v1.0"
            self.is_trained = True
        except (FileNotFoundError, EOFError, KeyError, pickle.UnpicklingError, json.JSONDecodeError):
            self.train()
            self.integrity = {"status": "verified", "verified": True}

    @staticmethod
    def _is_stale_demo_model(metadata: Dict[str, Any]) -> bool:
        """True only for a synthetic demo model whose dataset was since replaced.

        Real-data models are never replaced automatically: they change only
        through the reviewed candidate/activation workflow.
        """
        dataset = metadata.get("dataset") or {}
        if dataset.get("dataset_type") != "synthetic_demonstration" or not DATASET_PATH.exists():
            return False
        try:
            current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
        except json.JSONDecodeError:
            return False
        if current.get("dataset_type") != "synthetic_demonstration":
            return False
        return bool(dataset.get("sha256")) and dataset.get("sha256") != _dataset_sha256(DATASET_PATH)

    def get_metadata(self) -> Dict[str, Any]:
        return dict(self.training_metadata)

    @property
    def dataset_type(self) -> str:
        meta = self.training_metadata
        return (meta.get("dataset") or {}).get("dataset_type") or meta.get("dataset_type") or "unknown"

    @property
    def is_synthetic(self) -> bool:
        # Unknown provenance is treated as unvalidated, never as production-grade.
        return self.dataset_type in UNVALIDATED_DATASET_TYPES


_pipeline_instance: Optional[CRMSMLPipeline] = None


def get_pipeline() -> CRMSMLPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CRMSMLPipeline()
    return _pipeline_instance
