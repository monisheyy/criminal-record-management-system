# AI-CRMS Training Dataset Schema

## Bundled dataset

- File: `india_crime_training_v1.csv`
- Version: `india-2.0` (adds the case-detail columns; every other column is identical to `india-1.0`)
- Type: **synthetic demonstration data** (models trained on it can never be activated for real use)
- Rows: 6,000 incidents, dated 2018–2025
- Generator: `generate_india_dataset.py`, seed `42`. The SHA-256 is pinned in `dataset_manifest.json`
- Real personal data: **none**. No names, and no real people, cases or gangs

### What is realistic, and what is invented

| | |
|---|---|
| Crime mix | Follows the broad ordering of offence volumes in NCRB *Crime in India* reports: assault, vehicle theft and cheating are common; trafficking and money laundering are rare. Shares are indicative, not exact NCRB figures, and rare classes are raised to a 3% floor so the model sees enough examples. |
| Crime patterns | Each crime type has a consistent profile: weapon, drugs, money motive, technology, time of day, typical age and number of associates. |
| Case details | Type of place, target and modus operandi, as on an FIR. Each crime type has its own typical mix with overlaps (assault and murder are both mostly physical violence against a person), and 10% of entries are drawn at random to stand in for recording errors and unusual cases. Drawn from a separate random stream (seed 43). |
| Gangs | Six **fictional** gangs (`app.constants.GANG_NAMES`). Each specialises in a few crime types and has its own habits, such as age, crew size and night activity. Home states are assigned arbitrarily, so no region is singled out. |
| `reoffended_2y` | A **simulated** outcome (re-arrested within two years). It rises with prior convictions, gang membership, weapons, drugs, violence and offence severity, and falls with age. |
| `slice_state` | Indian state, used only for per-state error analysis. It is never a model input. |

Accuracy measured on this data shows that the models learn these designed
patterns. It says nothing about real-world accuracy, which only real case
data can establish (see `docs/MODEL_TRAINING.md`).

## Columns

| Column | Type | Range / values | Role |
|---|---|---|---|
| `prior_convictions` | numeric | 0–100 | feature |
| `age` | numeric | 16–100 | feature |
| `is_gang_member` | binary | 0/1 | feature (not used by the gang model) |
| `weapons_involved` | binary | 0/1 | feature |
| `drug_involvement` | binary | 0/1 | feature |
| `financial_motivation` | binary | 0/1 | feature |
| `tech_involvement` | binary | 0/1 | feature |
| `violence_history` | numeric | 0–100 | feature |
| `location_risk` | numeric | 0–1 | feature |
| `time_of_crime` | numeric | 0–23 | feature |
| `associates_count` | numeric | 0–1000 | feature |
| `location_<key>` × 6 | binary | 0/1, one column per `app.constants.LOCATION_TYPES` key; blank in all six = not recorded | feature |
| `target_<key>` × 6 | binary | 0/1, one per `TARGET_TYPES` key | feature |
| `method_<key>` × 9 | binary | 0/1, one per `MODUS_OPERANDI` key | feature |
| `crime_type` | categorical | 15 defined crime classes | target |
| `gang_label` | categorical | 6 gangs + `None` | target |

Datasets without the 21 case-detail columns (the 11 base features followed
directly by the two targets) still load; their case details count as missing.

### Optional columns (after the columns above, never model inputs)

| Column | Type | Role |
|---|---|---|
| `incident_date` | ISO 8601 date/time, required on every row if present | Enables the time-based holdout (newest 20% of cases) and time-series CV |
| `reoffended_2y` | 0/1, required on every row if present | Outcome for the learned danger score; without it the fixed-weight prototype score is used |
| `slice_<name>` | categorical text, blank = unknown | Group for per-slice error analysis only (e.g. `slice_state`) |

Using a real dataset instead of this one is described in
[docs/MODEL_TRAINING.md](../../../../docs/MODEL_TRAINING.md).

## Rebuilding the dataset

Run from `backend/`:

```bash
python -m app.ml.data.generate_india_dataset
```

The generator is deterministic (`seed=42`) and rewrites the CSV and manifest.
If the CSV differs from the manifest, the training loader rejects it rather
than silently training on an untracked dataset. A demo model trained on an
older version of the bundled dataset is retrained automatically at start-up.
