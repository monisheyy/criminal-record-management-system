# AI-CRMS Training Dataset Schema

## Dataset

- File: `demo_crime_training_v1.csv`
- Version: `1.0`
- Type: **synthetic demonstration data**
- Rows: 600
- Generator seed: `42`
- SHA-256: `3351c57fc7807e50f276e6ace954b7efb89fd23254787c8cea6fc17ac38ec526`
- Real personal data: **none**

The dataset preserves the feature schema used by the original AI-CRMS Random
Forest pipeline. It is suitable for demonstrating the software/ML pipeline,
not for real-world criminal-risk assessment or deployment.

## Columns

| Column | Type | Range / values | Role |
|---|---|---|---|
| `prior_convictions` | numeric | 0–100 | feature |
| `age` | numeric | 16–100 | feature |
| `is_gang_member` | binary | 0/1 | feature |
| `weapons_involved` | binary | 0/1 | feature |
| `drug_involvement` | binary | 0/1 | feature |
| `financial_motivation` | binary | 0/1 | feature |
| `tech_involvement` | binary | 0/1 | feature |
| `violence_history` | numeric | 0–100 | feature |
| `location_risk` | numeric | 0–1 | feature |
| `time_of_crime` | numeric | 0–23 | feature |
| `associates_count` | numeric | 0–1000 | feature |
| `crime_type` | categorical | 15 defined crime classes | target |
| `gang_label` | categorical | 5 gangs + `None` | target |

### Optional columns (after the 13 above, never model inputs)

| Column | Type | Role |
|---|---|---|
| `incident_date` | ISO 8601 date/time, required on every row if present | Enables the time-based holdout (newest 20% of cases) and time-series CV |
| `slice_<name>` | categorical text, blank = unknown | Group for per-slice error analysis only (e.g. `slice_district`) |

Using a real dataset instead of this one is described in
[docs/MODEL_TRAINING.md](../../../../docs/MODEL_TRAINING.md).

## Rebuilding the dataset

Run:

```bash
python app/ml/data/generate_demo_dataset.py
```

The generator is deterministic (`seed=42`) and rewrites the CSV and manifest.
If the generated file differs from the manifest, the training loader rejects
it rather than silently training on an untracked dataset.
