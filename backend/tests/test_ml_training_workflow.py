"""Training on real data: dataset context columns, time-based holdout,
calibration, manifest building, model comparison and case incident inputs."""
import argparse
import csv
import json
import random
import string
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.ml import pipeline as ml


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _write_dated_copy(tmp_path, *, extra_header=("incident_date", "slice_district"), blank_date_row=None, limit=None):
    """Copy the demo dataset's schema columns, appending an incident date and a district slice."""
    with ml.DATASET_PATH.open(newline="", encoding="utf-8") as handle:
        rows = [row[:len(ml.FEATURE_COLUMNS) + 2] for row in csv.reader(handle)]  # features + 2 targets
    if limit is not None:
        rows = rows[:limit + 1]
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    out = tmp_path / "dated.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(rows[0] + list(extra_header))
        for i, row in enumerate(rows[1:]):
            # Row order deliberately differs from date order.
            date = "" if i == blank_date_row else (start + timedelta(days=(i * 37) % len(rows))).isoformat()
            writer.writerow(row + [date, f"D{i % 3}"][:len(extra_header)])
    return out


def test_dataset_context_columns_are_loaded_but_never_features(tmp_path):
    X, y_crime, _, meta, context = ml.load_training_dataset(_write_dated_copy(tmp_path), with_context=True)
    assert X.shape[1] == len(ml.FEATURE_COLUMNS)
    assert meta["has_incident_dates"] is True
    assert meta["slice_columns"] == ["district"]
    assert len(context["incident_dates"]) == len(y_crime)
    assert set(context["slices"]["district"]) == {"D0", "D1", "D2"}


def test_unknown_extra_column_and_blank_date_are_rejected(tmp_path):
    with pytest.raises(ml.DatasetValidationError, match="columns do not match"):
        ml.load_training_dataset(_write_dated_copy(tmp_path, extra_header=("incident_date", "suspect_name")))
    with pytest.raises(ml.DatasetValidationError, match="incident_date"):
        ml.load_training_dataset(_write_dated_copy(tmp_path, blank_date_row=5))


def test_dated_dataset_uses_time_holdout_and_reports_slices(tmp_path):
    X, y_crime, y_gang, _, context = ml.load_training_dataset(_write_dated_copy(tmp_path), with_context=True)
    y_enc = ml.LabelEncoder().fit_transform(y_crime)
    train_idx, test_idx, kind = ml.holdout_split(y_enc, context["incident_dates"])
    assert kind == "time"
    assert context["incident_dates"][train_idx].max() <= context["incident_dates"][test_idx].min()
    assert len(test_idx) == int(np.ceil(len(X) * ml.TEST_SIZE))

    pipeline = ml.CRMSMLPipeline()
    metrics = pipeline.train(X, y_crime, y_gang, save=False, context=context)
    assert metrics["evaluation_method"].startswith("time-based holdout")
    assert metrics["crime_classifier"]["cross_validation"]["scheme"] == "time_series"
    districts = metrics["crime_classifier"]["subgroup_evaluation"]["slices"]["district"]
    assert {group["group"] for group in districts} == {"D0", "D1", "D2"}


def test_calibration_is_measured_persisted_and_used_for_predictions(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "CALIBRATION_METHOD", "sigmoid")
    monkeypatch.setattr(ml, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml, "METADATA_PATH", tmp_path / "metadata.json")
    pipeline = ml.CRMSMLPipeline()
    metrics = pipeline.train(save=True)
    calibration = metrics["crime_classifier"]["calibration"]
    assert calibration["method"] == "sigmoid"
    assert "uncalibrated_expected_calibration_error" in calibration

    reloaded = ml.CRMSMLPipeline()
    assert reloaded.crime_calibrator is not None
    result = reloaded.predict({"prior_convictions": 2, "weapons_involved": 1})
    assert "sigmoid-calibrated" in result["input_features"]["calibration_warning"]


def test_invalid_calibration_setting_fails_loudly(monkeypatch):
    monkeypatch.setattr(ml, "CALIBRATION_METHOD", "platt")
    with pytest.raises(ValueError, match="AI_CRMS_CALIBRATION"):
        ml.calibration_method()


def _manifest_args(dataset, **overrides):
    values = dict(dataset=dataset, dataset_type="authorized_historical", name="Test cases", version="1.0",
                  source="unit test", owner="tests", approval_ref="TEST-1", label_definition="final charge")
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_manifest_records_hash_and_refuses_unsafe_labels(tmp_path):
    from app.ml.build_manifest import BUNDLED_DEMO_DATASET, build_manifest

    dataset = _write_dated_copy(tmp_path, limit=600)
    manifest = build_manifest(_manifest_args(dataset))
    assert manifest["sha256"] == ml._dataset_sha256(dataset)
    assert manifest["dataset_type"] == "authorized_historical"
    assert manifest["optional_columns"] == ["incident_date", "slice_district"]
    assert any("fewer than" in warning for warning in manifest["warnings"])  # 600 rows / 15 classes

    with pytest.raises(SystemExit, match="must not be one of"):
        build_manifest(_manifest_args(dataset, dataset_type="synthetic_demonstration"))
    with pytest.raises(SystemExit, match="bundled synthetic demo"):
        build_manifest(_manifest_args(BUNDLED_DEMO_DATASET))


def test_compare_models_excludes_locked_holdout(monkeypatch):
    from app.ml import compare_models

    monkeypatch.setattr(compare_models, "CANDIDATES", {
        "majority_baseline": compare_models.CANDIDATES["majority_baseline"],
        "random_forest": compare_models.CANDIDATES["random_forest"],
    })
    report = compare_models.build_report()
    assert report["development_rows"] + report["holdout"]["rows_excluded"] == report["dataset"]["rows"]
    assert report["results"]["random_forest"]["folds_evaluated"] >= 2
    assert report["summary"]["best_by_macro_f1"] == "random_forest"
    # Scores on the demo data can reach the gate thresholds; activation is still
    # refused because of the dataset type, never because of the scores.
    assert report["dataset"]["dataset_type"] in ml.UNVALIDATED_DATASET_TYPES


def test_case_incident_facts_are_stored_and_used_as_observed_model_inputs(client, admin_token):
    title = "Incident facts " + "".join(random.choices(string.ascii_lowercase, k=6))
    created = client.post("/api/cases", json={
        "title": title, "weapons_involved": True, "drug_involvement": False,
    }, headers=_bearer(admin_token))
    assert created.status_code == 200, created.text
    case = created.json()
    assert case["weapons_involved"] is True and case["drug_involvement"] is False
    assert case["financial_motivation"] is None  # not recorded stays distinct from "no"

    r = client.post("/api/ai/predict", json={"case_id": case["id"]}, headers=_bearer(admin_token))
    assert r.status_code == 200, r.text
    quality = r.json()["input_features"]["feature_input_quality"]
    assert {"weapons_involved", "drug_involvement"} <= set(quality["observed_features"])
    assert {"financial_motivation", "tech_involvement"} <= set(quality["defaulted_features"])


def test_case_details_are_stored_and_drive_the_crime_suggestion(client, admin_token):
    title = "Case details " + "".join(random.choices(string.ascii_lowercase, k=6))
    created = client.post("/api/cases", json={
        "title": title, "location_type": "Online", "target_type": "data", "modus_operandi": "cyber_intrusion",
    }, headers=_bearer(admin_token))
    assert created.status_code == 200, created.text
    case = created.json()
    assert (case["location_type"], case["target_type"], case["modus_operandi"]) == ("online", "data", "cyber_intrusion")

    r = client.post("/api/ai/predict", json={"case_id": case["id"]}, headers=_bearer(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"location_online", "target_data", "method_cyber_intrusion"} <= set(
        body["input_features"]["feature_input_quality"]["observed_features"])
    assert body["predicted_crime_type"] == "Cybercrime"

    bad = client.post("/api/cases", json={"title": "Bad detail", "location_type": "moon"}, headers=_bearer(admin_token))
    assert bad.status_code == 422


def test_incident_facts_reject_non_boolean_values(client, admin_token):
    r = client.post("/api/cases", json={"title": "Bad incident fact", "weapons_involved": "maybe"},
                    headers=_bearer(admin_token))
    assert r.status_code == 422


def test_activation_refuses_unknown_provenance(client, admin_token):
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        record = models.MLModel(version="vtest-unknown", model_type="crime_classifier", is_active=False,
                                evaluation_metadata={"candidate_status": "awaiting_review",
                                                     "candidate_path": str(ml.CANDIDATES_DIR / "x"),
                                                     "dataset_type": "unknown",
                                                     "quality_gate": {"passed": True, "checks": []}})
        db.add(record)
        db.commit()
        model_id = record.id
    finally:
        db.close()
    r = client.post(f"/api/ai/models/{model_id}/activate",
                    json={"justification": "Attempting to activate an unknown-provenance candidate"},
                    headers=_bearer(admin_token))
    assert r.status_code == 409
    assert "unverified-provenance" in r.json()["detail"]
