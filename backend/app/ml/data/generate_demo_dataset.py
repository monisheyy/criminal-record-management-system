"""Generate the deterministic synthetic AI-CRMS demonstration training dataset.

This generator is demonstration-only and must not be interpreted as real criminal data.
"""
from pathlib import Path
import csv, hashlib, json
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUTPUT = DATA_DIR / "demo_crime_training_v1.csv"
SEED = 42
N_SAMPLES = 600
FEATURE_COLUMNS = ['prior_convictions', 'age', 'is_gang_member', 'weapons_involved', 'drug_involvement', 'financial_motivation', 'tech_involvement', 'violence_history', 'location_risk', 'time_of_crime', 'associates_count']
CRIME_TYPES = ['Robbery', 'Assault', 'Murder', 'Drug Trafficking', 'Burglary', 'Cybercrime', 'Fraud', 'Kidnapping', 'Arms Trafficking', 'Extortion', 'Human Trafficking', 'Car Theft', 'Vandalism', 'Arson', 'Money Laundering']
GANG_NAMES = ['Shadow Syndicate', 'Red Serpents', 'Iron Fist', 'Night Wolves', 'Black Eagles']

def generate_rows(n_samples=N_SAMPLES):
    rng = np.random.RandomState(SEED)
    rows=[]
    for _ in range(n_samples):
        prior_convictions=int(rng.randint(0,10)); age=int(rng.randint(16,65)); is_gang_member=int(rng.choice([0,1],p=[.6,.4])); weapons=int(rng.choice([0,1],p=[.5,.5])); drugs=int(rng.choice([0,1],p=[.6,.4])); financial=int(rng.choice([0,1],p=[.5,.5])); tech=int(rng.choice([0,1],p=[.7,.3])); violence=int(rng.randint(0,5)); location=float(rng.uniform(0,1)); time=int(rng.randint(0,24)); associates=int(rng.randint(0,15))
        weights=np.ones(len(CRIME_TYPES))
        if weapons:
            for i,c in enumerate(CRIME_TYPES):
                if c in ["Murder","Robbery","Arms Trafficking"]: weights[i]*=3
        if drugs: weights[CRIME_TYPES.index("Drug Trafficking")]*=4
        if financial:
            for i,c in enumerate(CRIME_TYPES):
                if c in ["Fraud","Extortion","Money Laundering"]: weights[i]*=3
        if tech: weights[CRIME_TYPES.index("Cybercrime")]*=4
        if is_gang_member:
            for i,c in enumerate(CRIME_TYPES):
                if c in ["Drug Trafficking","Arms Trafficking","Extortion"]: weights[i]*=2
        weights/=weights.sum()
        crime=str(rng.choice(CRIME_TYPES,p=weights))
        gang=str(rng.choice(GANG_NAMES)) if is_gang_member else "None"
        rows.append([prior_convictions,age,is_gang_member,weapons,drugs,financial,tech,violence,round(location,8),time,associates,crime,gang])
    return rows

def write_dataset(rows):
    cols=FEATURE_COLUMNS+["crime_type","gang_label"]
    with OUTPUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(cols); w.writerows(rows)
    digest=hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest={
      "dataset_name":"AI-CRMS Demonstration Crime Training Dataset",
      "dataset_version":"1.0",
      "dataset_type":"synthetic_demonstration",
      "generated_with_seed":SEED,
      "rows":len(rows),
      "feature_columns":FEATURE_COLUMNS,
      "target_columns":["crime_type","gang_label"],
      "sha256":digest,
      "source":"Deterministic synthetic generator derived from the original AI-CRMS demo pipeline. No real criminal personal data.",
      "schema_version":"1.0"
    }
    (DATA_DIR/"dataset_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__ == "__main__":
    write_dataset(generate_rows())
    print(f"Wrote {OUTPUT}")
