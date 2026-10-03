"""Training on this system's own cases: exporter output, and inference that
treats unrecorded inputs exactly as training did (no train/serve skew)."""
import csv
import json
import uuid
from datetime import date, datetime, timezone

import numpy as np

from app import models
from app.ml import export_training_data as export
from app.ml.model_inputs import model_input
from app.ml.pipeline import CRMSMLPipeline, FEATURE_COLUMNS, load_training_dataset

COL = {name: i for i, name in enumerate(FEATURE_COLUMNS)}


def test_unrecorded_inputs_are_missing_not_defaults_when_imputing():
    case_only = {"crime_type": None, "prior_convictions": None, "weapons_involved": 1,
                 "incident_date": "2025-03-04T21:15:00+00:00"}
    features = CRMSMLPipeline._extract_features(case_only, impute_missing=True)
    assert features[COL["weapons_involved"]] == 1.0
    assert features[COL["time_of_crime"]] == 21.0  # derived from the timestamp, not imputed
    for name in ("prior_convictions", "age", "is_gang_member", "drug_involvement", "associates_count"):
        assert np.isnan(features[COL[name]]), name

    # Legacy mode (models without imputers) keeps the documented defaults.
    legacy = CRMSMLPipeline._extract_features(case_only)
    assert legacy[COL["drug_involvement"]] == 0.0 and legacy[COL["is_gang_member"]] == 0.0


def test_age_is_measured_at_the_incident():
    person = {"date_of_birth": "1990-06-01"}
    at_2010 = CRMSMLPipeline._extract_features({**person, "incident_date": "2010-07-01T00:00:00"})
    assert at_2010[COL["age"]] == 20


def test_prediction_with_sparse_inputs_reports_imputed_values_as_valid_json():
    pipeline = CRMSMLPipeline()
    result = pipeline.predict({"crime_type": None, "prior_convictions": None})
    rows = result["input_features"]["explanation"]["all_features"]
    json.dumps(result, allow_nan=False)  # NaN would break the API response
    imputed = {row["feature"] for row in rows if row["imputed"]}
    assert {"weapons_involved", "prior_convictions", "is_gang_member"} <= imputed


def _closed_case(db, *, crime_type="Robbery", when=None, station="Harbor PS", **facts):
    case = models.Case(
        case_number=f"T-{uuid.uuid4().hex[:10]}", title="Export test", crime_type=crime_type,
        status=models.CaseStatus.closed, incident_date=when, fir_station=station, **facts,
    )
    db.add(case)
    db.flush()
    return case


def _criminal(db, **fields):
    criminal = models.Criminal(crn=f"CRN-{uuid.uuid4().hex[:10]}", first_name="Test", last_name="Person", **fields)
    db.add(criminal)
    db.flush()
    return criminal


def test_export_rows_match_live_prediction_inputs(db, tmp_path):
    when = datetime(2024, 5, 6, 23, 10, 0, 123456, tzinfo=timezone.utc)
    case = _closed_case(db, when=when, weapons_involved=True, drug_involvement=False)
    witness = _criminal(db, prior_convictions=9)
    accused = _criminal(db, prior_convictions=2, date_of_birth=date(1994, 1, 1), known_associates="a, b")
    db.add_all([
        models.CaseCriminal(case_id=case.id, criminal_id=witness.id, role="witness"),
        models.CaseCriminal(case_id=case.id, criminal_id=accused.id, role="accused"),
    ])
    db.add(_closed_case(db, crime_type="Unclassified", when=when))
    db.add(_closed_case(db, when=None))
    db.flush()
    db.expire_all()

    result = export.build_rows(db)
    mine = [row for row in result["rows"] if row["incident_date"] == when.replace(tzinfo=None).isoformat()
            or row["incident_date"] == when.isoformat()]
    assert len(mine) == 1
    row = mine[0]
    assert row["crime_type"] == "Robbery" and row["gang_label"] == "None"
    assert row["prior_convictions"] == "2"  # the accused, never the witness
    assert row["age"] == "30" and row["associates_count"] == "2" and row["time_of_crime"] == "23"
    assert row["weapons_involved"] == "1" and row["drug_involvement"] == "0"
    assert row["financial_motivation"] == "" and row["location_risk"] == ""  # unrecorded stays blank
    assert row["slice_station"] == "Harbor PS"
    assert result["skipped"]["no incident date"] >= 1
    assert result["skipped"]["no verified crime category (blank, Other or Unclassified)"] >= 1

    # Identical to the features a live prediction on this case would use.
    case = db.get(models.Case, case.id)
    live = CRMSMLPipeline._extract_features(model_input(db.get(models.Criminal, accused.id), case), impute_missing=True)
    exported = [float(row[name]) if row[name] else np.nan for name in FEATURE_COLUMNS]
    np.testing.assert_array_equal(live, exported)

    # The written CSV loads with the training loader, blanks as missing values.
    out = tmp_path / "export.csv"
    export.write_csv(mine * 100, out)
    X, y_crime, _, meta, context = load_training_dataset(out, with_context=True)
    assert X.shape == (100, len(FEATURE_COLUMNS)) and meta["missing_counts"]["location_risk"] == 100
    assert meta["slice_columns"] == ["station"] and context["incident_dates"] is not None
    with out.open(newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle))[-2:] == ["incident_date", "slice_station"]


def test_readiness_flags_small_and_unrecorded_data():
    rows = [{**{name: "" for name in FEATURE_COLUMNS}, "crime_type": "Fraud", "age": "40"}] * 3
    report = export.readiness(rows)
    text = " ".join(report["warnings"])
    assert report["rows"] == 3 and report["class_counts"] == {"Fraud": 3}
    assert "at least 100" in text and "Under 100 cases for: Fraud" in text
    assert "Never recorded" in text and "weapons_involved" in text
    assert report["recorded_percent"]["age"] == 100.0
