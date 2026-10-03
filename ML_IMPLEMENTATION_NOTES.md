> **Note (Oct 2026):** activation now also requires a passing quality gate and a written justification, artifacts are signed and verified before loading, and rollback is supported. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md) and [docs/AUDIT_REMEDIATION.md](docs/AUDIT_REMEDIATION.md).

# AI-CRMS ML Safety and Evaluation Update

## Scope

This update preserves the existing React/FastAPI/SQLAlchemy application and current model artifacts. It makes targeted changes to inference feature extraction, model retraining, and model-output handling.

## Changes

1. **Target-independent inference features**
   - `_extract_features()` no longer derives weapons, drug, financial, or technology features from `crime_type`.
   - These features must be supplied as explicit observed values. Missing values use documented defaults; numeric values are range-validated.
   - The bundled synthetic dataset remains a demonstration dataset and does not establish real-world predictive performance.

2. **Candidate-only retraining**
   - `POST /api/ai/retrain` trains a separate candidate and stores its artifacts under `backend/app/ml/saved_models/candidates/`.
   - Retraining does not overwrite the active model files or mutate the loaded active pipeline.
   - Candidate evaluation metadata is stored with the existing `MLModel` database record and the record is marked inactive.

3. **Controlled activation**
   - `POST /api/ai/models/{model_id}/activate` is admin-only and only accepts a candidate awaiting review.
   - Candidates trained on the bundled `synthetic_demonstration` dataset are explicitly blocked from activation.
   - Promotion validates the candidate path and artifact completeness, stages files, retains a temporary backup during promotion, and reloads the active pipeline.

4. **Human review for risk-related outputs**
   - A prediction no longer automatically overwrites `Criminal.risk_score` or `Criminal.threat_level`.
   - High prototype scores create review notifications with language clarifying that the score is unvalidated decision support, not a finding of dangerousness.

5. **Regression tests**
   - Added tests that ensure target labels do not affect extracted model features, explicit observations are used, and candidate saving leaves active artifacts unchanged.
   - Updated the retraining API test to assert that the active model is unchanged and the new model is a candidate.

## Verification

- Python compilation: passed.
- Previous package isolated ML tests: 18 passed.
- Updated isolated ML pipeline tests: 24 passed; scikit-learn still reports expected undefined-precision warnings for classes with no predicted samples, which are also explicitly surfaced in evaluation metadata.
- Frontend workflow tests: 5 passed.
- Evaluation smoke test: completed; synthetic demo crime accuracy 15.0% (majority baseline 13.3%, balanced accuracy 10.3%, macro-F1 9.3%); gang accuracy 54.2% (majority baseline 56.7%, balanced accuracy 20.6%, macro-F1 19.7%) after removing the direct target proxy. These figures describe only the synthetic demo split.
- Full project pytest collection could not run in the current environment because `python-jose` is not installed and package installation was unavailable due network/DNS restrictions. Run the full suite in the project's normal virtual environment after installing `backend/requirements.txt`.

## Important limitations

- The included training data is synthetic and must not be used to justify real-world criminal risk decisions.
- Current database records do not provide all eleven model features. Missing feature inputs therefore use defaults; model quality will remain limited until the feature contract is mapped to legitimate, available case evidence and evaluated on authorized, representative data.
- No new real-world performance claims are made. Candidate activation is blocked for synthetic-demo models.

## Next-phase feature-contract and evaluation work

6. **Feature-to-schema mapping**
   - Added `backend/app/ml/FEATURE_CONTRACT.md` documenting each of the eleven model features, current schema sources, missing structured fields, provenance requirements, and limitations.
   - Existing `Case.incident_date` is used as the source for `time_of_crime` when available; crime type is not used to derive the feature.
   - The gang classifier excludes `is_gang_member`, because the existing gang label is directly related to that feature. Legacy eleven-feature gang artifacts are disabled at inference and return a visible warning instead of an unreliable gang label.
   - Pipeline version bumped to 2.0 for the incompatible gang feature-schema change. Candidate activation validates pipeline version and exact per-model feature schemas, rejecting legacy candidates.
   - The prediction input metadata now reports observed, derived, and defaulted features with a coverage percentage and warning. This is data completeness, not probability calibration or evidence reliability.
   - The prediction UI surfaces model-validity, gang-model-availability, and input-completeness warnings.
   - The prediction router preserves a null `prior_convictions` value as missing and passes incident timestamps when a case is selected.

7. **Evaluation quality improvements**
   - Holdout metrics now include balanced accuracy, macro precision/recall/F1, majority-class baseline, predicted class distribution, and explicit zero-recall classes.
   - Added `backend/app/ml/evaluate_dataset.py`, a reproducible command that trains in memory, reports class distributions and metrics, and explicitly marks the bundled synthetic dataset as ineligible for operational release. It never saves/activates a model.
   - Added tests for class-imbalance metrics, input completeness reporting, deriving hour from a recorded incident timestamp, exclusion of the target-leaking gang feature, and disabling legacy gang artifacts.

8. **Run evaluation locally**
   From the `backend` directory after installing requirements:

   ```bash
   python -m app.ml.evaluate_dataset --output ml_evaluation_report.json
   pytest -q tests/test_ml_pipeline.py
   pytest -q
   ```

   The report is diagnostic only. The demo generator creates labels probabilistically from synthetic feature patterns; a higher score on this generated data does not validate real-world use. Do not activate models trained on it.
