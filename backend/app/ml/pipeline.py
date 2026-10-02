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
import json
import os
import pickle
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "saved_models"
CANDIDATES_DIR = MODEL_DIR / "candidates"
DATA_DIR = BASE_DIR / "data"
DATASET_PATH = DATA_DIR / "demo_crime_training_v1.csv"
MANIFEST_PATH = DATA_DIR / "dataset_manifest.json"
METADATA_PATH = MODEL_DIR / "metadata.json"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 42
TEST_SIZE = 0.20
DATASET_VERSION = "1.0"
PIPELINE_VERSION = "2.0"
CV_FOLDS = 5

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

CRIME_TYPES = [
    "Robbery", "Assault", "Murder", "Drug Trafficking", "Burglary",
    "Cybercrime", "Fraud", "Kidnapping", "Arms Trafficking", "Extortion",
    "Human Trafficking", "Car Theft", "Vandalism", "Arson", "Money Laundering",
]
CRIME_CATEGORIES = {
    "Robbery": "Violent", "Assault": "Violent", "Murder": "Violent",
    "Kidnapping": "Violent", "Drug Trafficking": "Narcotics",
    "Arms Trafficking": "Weapons", "Human Trafficking": "Organized Crime",
    "Fraud": "Financial", "Money Laundering": "Financial", "Extortion": "Financial",
    "Burglary": "Property", "Car Theft": "Property", "Vandalism": "Property",
    "Arson": "Property", "Cybercrime": "Technology",
}
GANG_NAMES = ["Shadow Syndicate", "Red Serpents", "Iron Fist", "Night Wolves", "Black Eagles"]
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


def load_training_dataset(path: Path = DATASET_PATH) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """Load and validate the versioned CSV training dataset."""
    if not path.exists():
        raise FileNotFoundError(f"Training dataset not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected_columns = FEATURE_COLUMNS + TARGET_COLUMNS
        if reader.fieldnames != expected_columns:
            raise DatasetValidationError(
                f"Dataset columns do not match schema. Expected {expected_columns}, got {reader.fieldnames}"
            )

        rows: List[List[float]] = []
        crime_labels: List[str] = []
        gang_labels: List[str] = []
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
    if MANIFEST_PATH.exists() and path.resolve() == DATASET_PATH.resolve():
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
    }
    return X, y_crime, y_gang, metadata


class CRMSMLPipeline:
    def __init__(self):
        self.crime_classifier = None
        self.gang_predictor = None
        self.label_encoder_crime = LabelEncoder()
        self.label_encoder_gang = LabelEncoder()
        self.imputer: Optional[SimpleImputer] = None
        self.scaler = StandardScaler()
        self.model_version = "v1.0"
        self.is_trained = False
        self.training_metadata: Dict[str, Any] = {}
        self._load_or_train()

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
    ) -> Dict[str, Any]:
        """Train and rigorously evaluate both classifiers on a deterministic holdout.

        The holdout metrics are the authoritative persisted evaluation metrics.
        Five-fold stratified cross-validation is additionally reported as a
        reproducibility/robustness diagnostic when every class has enough samples.
        """
        if X is None:
            X, y_crime, y_gang, dataset_meta = load_training_dataset()
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

        indices = np.arange(len(X))
        crime_train_idx, crime_test_idx = train_test_split(
            indices, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y_crime_enc
        )
        gang_train_idx, gang_test_idx = train_test_split(
            indices, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y_gang_enc
        )

        # Fit preprocessing only on each training split. This prevents test-set leakage.
        self.imputer = SimpleImputer(strategy="median")
        X_crime_train = self.imputer.fit_transform(X[crime_train_idx])
        X_crime_test = self.imputer.transform(X[crime_test_idx])
        self.scaler = StandardScaler()
        X_crime_train_scaled = self.scaler.fit_transform(X_crime_train)
        X_crime_test_scaled = self.scaler.transform(X_crime_test)

        self.crime_classifier = RandomForestClassifier(
            n_estimators=150, max_depth=10, random_state=RANDOM_SEED, class_weight="balanced"
        )
        self.crime_classifier.fit(X_crime_train_scaled, y_crime_enc[crime_train_idx])
        crime_pred = self.crime_classifier.predict(X_crime_test_scaled)
        crime_metrics = self._metrics(
            y_crime_enc[crime_test_idx], crime_pred, len(crime_train_idx), len(crime_test_idx),
            self.label_encoder_crime.classes_
        )
        crime_cv = self._cross_validation(
            X, y_crime_enc, self.label_encoder_crime.classes_,
            RandomForestClassifier(n_estimators=150, max_depth=10, random_state=RANDOM_SEED, class_weight="balanced")
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
        gang_metrics["cross_validation"] = self._cross_validation(
            X_gang, y_gang_enc, self.label_encoder_gang.classes_,
            RandomForestClassifier(n_estimators=100, max_depth=8, random_state=RANDOM_SEED, class_weight="balanced")
        )

        # Persist the crime preprocessing used by the prediction API. The gang model
        # has the same raw feature schema and deterministic preprocessing, but its
        # fitted transformer is retained separately for correct gang predictions.
        self.gang_imputer = gang_imputer
        self.gang_scaler = gang_scaler

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
            "evaluation_method": "stratified 80/20 holdout + 5-fold stratified cross-validation",
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
            "risk_level_thresholds": {"medium": 35, "high": 55, "critical": 75},
            "risk_score_disclaimer": "Prototype decision-support score; not clinically or legally validated.",
            "sklearn_version": sklearn.__version__,
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
    def _cross_validation(X: np.ndarray, y: np.ndarray, classes: Sequence[str], estimator: RandomForestClassifier) -> Dict[str, Any]:
        min_class_count = min(np.bincount(y))
        folds = min(CV_FOLDS, int(min_class_count))
        if folds < 2:
            return {"enabled": False, "reason": "At least two samples per class are required."}
        pipeline = SklearnPipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ])
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_SEED)
        scores = cross_validate(
            pipeline, X, y, cv=cv,
            scoring={"accuracy": "accuracy", "precision": "precision_weighted", "recall": "recall_weighted", "f1": "f1_weighted"},
            n_jobs=1,
        )
        return {
            "enabled": True,
            "folds": folds,
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
        features = self._extract_features(criminal_data)
        feature_quality = self._feature_input_quality(criminal_data)
        X_scaled = self._transform_features(np.array([features], dtype=float))

        crime_proba = self.crime_classifier.predict_proba(X_scaled)[0]
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
                    "The loaded model is trained on synthetic demonstration data and has not been validated for real-world use."
                    if (self.training_metadata.get("dataset", {}).get("dataset_type") == "synthetic_demonstration"
                        or self.training_metadata.get("dataset_type") == "synthetic_demonstration")
                    else None
                ),
                "risk_factors": risk_factors,
                "risk_score_method": {
                    "type": "deterministic_weighted_prototype",
                    "weights": RISK_SCORE_CONFIG,
                    "disclaimer": "Prototype decision-support score; not clinically or legally validated.",
                },
                "explanation": explanation,
            },
        }

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
        rows = []
        for name, value, importance in zip(FEATURE_COLUMNS, features, relative):
            rows.append({
                "feature": name,
                "value": round(float(value), 4),
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

    def _extract_features(self, data: Dict) -> List[float]:
        """Build inference features only from observed inputs, never from the target.

        The previous implementation inferred weapons/drug/financial/technology
        features from ``crime_type``. Since crime_type is the prediction target in
        the crime classifier, that created target leakage and made inference depend
        on the answer it was supposed to predict. Missing fields use documented,
        conservative defaults; callers can provide explicit feature values when
        those observations are available.
        """
        age = 30
        if data.get("date_of_birth"):
            try:
                dob_value = data["date_of_birth"]
                dob = (datetime.fromisoformat(dob_value.replace("Z", "+00:00"))
                       if isinstance(dob_value, str) else dob_value)
                age = (RISK_REFERENCE_DATE - dob.replace(tzinfo=None).date()).days // 365
            except (TypeError, ValueError, AttributeError):
                age = 30
        elif data.get("age") is not None:
            try:
                age = int(data["age"])
            except (TypeError, ValueError):
                raise ValueError("age must be numeric") from None
            if age < 16 or age > 100:
                raise ValueError("age must be between 16 and 100")

        def numeric(name: str, default: float, low: float, high: float) -> float:
            raw = data.get(name, default)
            try:
                value = float(default if raw in (None, "") else raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not np.isfinite(value) or value < low or value > high:
                raise ValueError(f"{name} must be between {low} and {high}")
            return value

        prior = numeric("prior_convictions", 0.0, 0.0, 100.0)
        gang_member = data.get("is_gang_member", bool(data.get("gang_id")))
        if not isinstance(gang_member, (bool, np.bool_, int, np.integer, float, np.floating)) or gang_member not in (0, 1, False, True):
            raise ValueError("is_gang_member must be boolean or 0/1")
        associates_default = min(len([x for x in (data.get("known_associates") or "").split(",") if x.strip()]), 15)
        return [
            prior,
            float(max(16, min(70, age))),
            float(bool(gang_member)),
            numeric("weapons_involved", 0.0, 0.0, 1.0),
            numeric("drug_involvement", 0.0, 0.0, 1.0),
            numeric("financial_motivation", 0.0, 0.0, 1.0),
            numeric("tech_involvement", 0.0, 0.0, 1.0),
            numeric("violence_history", 0.0, 0.0, 100.0),
            numeric("location_risk", 0.3, 0.0, 1.0),
            numeric("time_of_crime", float(self._incident_hour(data, default=12)), 0.0, 23.0),
            numeric("associates_count", float(associates_default), 0.0, 1000.0),
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
            target_raw = np.asarray(self._extract_features(criminal_data), dtype=float).reshape(1, -1)
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
                candidate_raw = np.asarray(self._extract_features(criminal), dtype=float).reshape(1, -1)
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
                "gang_scaler": getattr(self, "gang_scaler", self.scaler),
                "gang_imputer": getattr(self, "gang_imputer", self.imputer),
                "feature_columns": FEATURE_COLUMNS,
                "gang_feature_columns": GANG_FEATURE_COLUMNS,
            }, handle, protocol=pickle.HIGHEST_PROTOCOL)
        (output_dir / "metadata.json").write_text(
            json.dumps(self.training_metadata, indent=2), encoding="utf-8"
        )
        if output_dir.resolve() == MODEL_DIR.resolve():
            METADATA_PATH.write_text(json.dumps(self.training_metadata, indent=2), encoding="utf-8")

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
            self.gang_scaler = enc.get("gang_scaler", self.scaler)
            self.gang_imputer = enc.get("gang_imputer", self.imputer)
            if METADATA_PATH.exists():
                self.training_metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
                self.model_version = self.training_metadata.get("model_version", "v1.0")
            else:
                self.training_metadata = {"model_version": "v1.0", "legacy_artifact": True}
                self.model_version = "v1.0"
            self.is_trained = True
        except (FileNotFoundError, EOFError, KeyError, pickle.UnpicklingError, json.JSONDecodeError):
            self.train()

    def get_metadata(self) -> Dict[str, Any]:
        return dict(self.training_metadata)


_pipeline_instance: Optional[CRMSMLPipeline] = None


def get_pipeline() -> CRMSMLPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CRMSMLPipeline()
    return _pipeline_instance
