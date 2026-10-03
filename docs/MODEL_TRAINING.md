# Training the crime-type model on real data

This runbook takes the AI from the bundled synthetic demo data to a model that can pass the release gate. Every step runs from `backend/`. Read [MODEL_CARD.md](MODEL_CARD.md) and [FEATURE_CONTRACT.md](../backend/app/ml/FEATURE_CONTRACT.md) first.

> The bundled demo dataset has **no learnable signal**: every model scores at chance level (macro-F1 ≈ 0.08–0.10 against 1/15 ≈ 0.07). No candidate trained on it can, or should, pass the gate. Real performance depends entirely on real data.

## 1. Define the task

Task: *suggest the likely offence category for a new case from its incident details*, as a triage aid that an officer confirms or overrides. Before collecting data, write down and get sign-off on:

- **who** sees the suggestion (investigating officer) and **what decision** it supports (triage/routing, never charging);
- **the time point**: which facts are known when the suggestion is made. Every training feature must be as of that point;
- **cost of errors**: which confusions are harmful (e.g. Assault vs Murder), so you can check them in the confusion matrix.

## 2. Assemble a lawful dataset

### Option A: export this system's own closed cases (recommended)

```bash
python -m app.ml.export_training_data --output /secure/data/cases_v1.csv
```

Every closed or archived case with a verified offence category and an incident date becomes one row, already in the training schema with `incident_date` and a `slice_station` column. Features are built by the same code as live predictions (`app/ml/model_inputs.py`), so the model is trained on exactly what it will see. Unrecorded facts are left blank. The command prints cases per category, how often each feature was recorded, and warnings. It exits non-zero until there are at least 100 usable cases.

Before you rely on it:

- **Close cases with the final category.** Only `closed`/`archived` cases are used, and `Other`/`Unclassified` are skipped, so set `crime_type` to the verified outcome when closing.
- **Record the Incident facts** (weapon, drugs, financial motive, technology) on every case. A feature that is never recorded carries no signal; the export warns about it.
- **Link offenders with a role.** Features describe the case's `convicted` → `primary_offender` → `accused` → `accomplice` → `suspect` person, in that order; witnesses are never used.
- **Check `prior_convictions` for leakage.** It is the offender's *current* count, which can include the conviction for this very case. Where possible, reduce it to the count before the incident.

### Option B: an external dataset

- Source: historical closed case files from this system or a partner agency, with written legal approval and a data-protection impact assessment.
- Label (`crime_type`): the **final verified** outcome (charge-sheet or conviction category), never the first guess at FIR time. Values must come from `app.constants.CRIME_TYPES`. Map or merge local categories onto it.
- Size: aim for **≥ 100 rows per category** (hundreds is better). Merge or drop rare categories; the gate fails any category the model never gets right.
- Format: the 13 columns in [DATASET_SCHEMA.md](../backend/app/ml/data/DATASET_SCHEMA.md), then add:
  - `incident_date` (strongly recommended) to get an honest time-based holdout;
  - `slice_<name>` columns (e.g. `slice_district`, or legally permissible group attributes) for per-group error analysis. They are never model inputs.
- Hygiene: remove duplicates, keep a record of where each row came from, and never edit the file after step 3.
- Leave a feature **blank** when it was not recorded; blank values are median-imputed and counted in the manifest. Do not write 0 for "unknown".

## 3. Freeze it with a manifest

```bash
python -m app.ml.build_manifest --dataset /secure/data/cases_v1.csv \
  --dataset-type authorized_historical --name "District case outcomes" --version 1.0 \
  --source "CRMS export 2020-2025, closed cases, final charge category" \
  --owner "Records unit" --approval-ref "DPIA-2026-014" \
  --label-definition "Final charge-sheet offence category"
```

This validates the file, records its SHA-256 and provenance, and prints warnings (small classes, duplicates, missing dates or slices, heavily missing columns). Fix the warnings and rebuild with `--force`. Training refuses the CSV if it changes after this.

Then point the server at it (in `.env`):

```
AI_CRMS_DATASET_PATH=/secure/data/cases_v1.csv
```

`synthetic_demonstration`, `unknown` and `external` dataset types can never be activated.

## 4. Choose the model without touching the holdout

```bash
python -m app.ml.compare_models --output reports/compare_v1.json
```

This compares the majority baseline, Random Forest (raw, sigmoid- and isotonic-calibrated) and gradient boosting, using only the **development** portion. The locked holdout (newest 20% of cases when dated) is excluded and judged once, by the gate, in step 6.

Read the output:

- If the best model does not clearly beat the baseline, or is far below the gate thresholds, **stop**. More or better features or data are needed; tuning won't fix that.
- Set `AI_CRMS_CALIBRATION` to the suggested value (the lowest calibration error that doesn't cost macro-F1).
- If gradient boosting wins by more than the fold standard deviation, switching `crime_estimator()` in `pipeline.py` is the follow-up change.

## 5. Check fairness and reliability

```bash
python -m app.ml.evaluate_dataset --output reports/readiness_v1.json
```

Check `subgroup_evaluation` for large accuracy gaps between districts, groups and time periods (slices under 10 rows are not scored), and check the reliability table under `calibration`. Document any gap and the mitigation before release.

## 6. Release through the gate

1. **Model Governance → Train candidate.** This trains on the configured dataset and evaluates on the locked holdout once. The active model is not changed.
2. The candidate must pass the gate: macro-F1 ≥ 0.60, balanced accuracy ≥ 0.60, no zero-recall categories, ECE ≤ 0.15, ≥ 100 holdout rows, beats the majority baseline.
3. An admin activates it with a written justification (audited). Artifacts are signed with `SECRET_KEY`, so keep that key stable.

If the gate fails, do **not** retrain repeatedly against the same holdout until it passes: that turns the holdout into training data. Go back to step 2 or 4, and when you change the data, freeze a new dataset version.

## 7. Monitor after launch

- Track the confirm/override rate of reviews (AI Predictions page). Rising overrides mean the model has drifted.
- Fill in the **Incident facts** on every case (weapon, drugs, financial motive, technology). Unrecorded facts are defaulted and flagged in each prediction's input-quality panel.
- Retrain on a schedule with a new dataset version (new manifest), and use **Roll back** if the new version does worse.
- Never use model outputs or unreviewed predictions as training labels.
