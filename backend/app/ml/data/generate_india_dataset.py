"""Generate the deterministic synthetic India demonstration training dataset.

Run from backend/:
    python -m app.ml.data.generate_india_dataset

Every row is invented. No real person, case or gang is represented: the six
gangs are fictional, and the generator creates no names (the training schema
has none). What is realistic is the *structure*:

* The crime mix follows the broad ordering of offence volumes in NCRB's
  "Crime in India" reports (hurt/assault, vehicle theft and cheating among the
  most common; trafficking and money laundering among the rarest). The shares
  are indicative, not exact NCRB figures, and rare categories are raised to a
  floor so the model sees enough examples of each.
* Each crime type has a consistent profile (weapons, drugs, money motive,
  technology, time of day, typical age, number of associates), and each gang
  specialises in a few crime types with its own habits. That gives the model
  real patterns to learn, so its accuracy on this data is meaningful *for
  this data only*.
* ``reoffended_2y`` is a simulated outcome (re-arrested within two years)
  driven mainly by prior convictions, age, gang membership and violence, used
  to train the learned danger score.

States are only an analysis slice (``slice_state``), never a model input, and
gang home states are spread arbitrarily so no region is singled out.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.constants import CRIME_TYPES, GANG_NAMES

DATA_DIR = Path(__file__).resolve().parent
OUTPUT = DATA_DIR / "india_crime_training_v1.csv"
MANIFEST = DATA_DIR / "dataset_manifest.json"
SEED = 42
N_SAMPLES = 6000
GANG_MEMBER_SHARE = 0.30
SPECIALTY_SHARE = 0.85  # how often a gang member's crime is one of the gang's specialties
START, END = date(2018, 1, 1), date(2025, 12, 31)

FEATURE_COLUMNS = ["prior_convictions", "age", "is_gang_member", "weapons_involved", "drug_involvement",
                   "financial_motivation", "tech_involvement", "violence_history", "location_risk",
                   "time_of_crime", "associates_count"]
COLUMNS = FEATURE_COLUMNS + ["crime_type", "gang_label", "incident_date", "slice_state", "reoffended_2y"]

# Indicative relative volumes (NCRB ordering, rare categories floored at 3%).
CRIME_MIX = {
    "Assault": 14, "Car Theft": 12, "Fraud": 11, "Burglary": 8, "Kidnapping": 8, "Drug Trafficking": 8,
    "Cybercrime": 7, "Arms Trafficking": 6, "Robbery": 5, "Murder": 4, "Vandalism": 4, "Arson": 3,
    "Extortion": 3, "Human Trafficking": 3, "Money Laundering": 3,
}

# Per-crime profile: probability of weapons / drugs / money motive / technology,
# probability the incident is at night, mean age, mean associates, mean violence history.
CRIME_PROFILES = {
    #                    weapons drugs  money  tech   night  age  assoc viol
    "Robbery":           (0.70, 0.10, 0.85, 0.05, 0.65, 27, 3.0, 2.0),
    "Assault":           (0.35, 0.15, 0.05, 0.02, 0.55, 30, 1.5, 2.5),
    "Murder":            (0.80, 0.10, 0.20, 0.03, 0.55, 33, 2.0, 3.5),
    "Drug Trafficking":  (0.25, 0.95, 0.80, 0.15, 0.50, 29, 5.0, 1.2),
    "Burglary":          (0.10, 0.05, 0.80, 0.02, 0.80, 26, 1.5, 0.6),
    "Cybercrime":        (0.02, 0.02, 0.80, 0.97, 0.30, 25, 2.0, 0.2),
    "Fraud":             (0.02, 0.03, 0.95, 0.45, 0.15, 38, 2.0, 0.2),
    "Kidnapping":        (0.65, 0.05, 0.60, 0.20, 0.50, 30, 4.0, 2.5),
    "Arms Trafficking":  (0.95, 0.20, 0.80, 0.10, 0.55, 32, 5.0, 2.0),
    "Extortion":         (0.55, 0.05, 0.95, 0.35, 0.40, 31, 4.0, 2.2),
    "Human Trafficking": (0.25, 0.20, 0.90, 0.40, 0.45, 36, 6.0, 1.2),
    "Car Theft":         (0.08, 0.05, 0.75, 0.20, 0.75, 24, 2.0, 0.5),
    "Vandalism":         (0.05, 0.25, 0.05, 0.02, 0.70, 21, 2.0, 0.8),
    "Arson":             (0.15, 0.10, 0.25, 0.02, 0.75, 29, 1.5, 1.5),
    "Money Laundering":  (0.02, 0.10, 0.98, 0.65, 0.10, 43, 4.0, 0.2),
}
FACT_NAMES = ("weapons_involved", "drug_involvement", "financial_motivation", "tech_involvement")

# Fictional gangs. "specialties" are crime types with relative weights; the
# habits (age shift, night preference, extra associates, extra fact tendencies)
# make gangs that share a crime type still distinguishable.
GANGS = {
    "Kaala Bichhoo Gang": {
        "alias": "KBG, The Black Scorpions", "territory": "Mumbai, Kochi", "states": ["Maharashtra", "Kerala"],
        "threat_level": "critical", "known_activities": "Narcotics supply, arms smuggling, hawala money movement",
        "specialties": {"Drug Trafficking": 0.5, "Arms Trafficking": 0.25, "Money Laundering": 0.25},
        "age_shift": 4, "night": 0.70, "assoc": 4.0, "facts": {"drug_involvement": 0.10},
    },
    "Lal Toofan Crew": {
        "alias": "LTC, Red Storm", "territory": "Delhi NCR, Jaipur", "states": ["Delhi", "Rajasthan"],
        "threat_level": "high", "known_activities": "Highway robbery, vehicle theft, house break-ins",
        "specialties": {"Robbery": 0.4, "Car Theft": 0.35, "Burglary": 0.25},
        "age_shift": -4, "night": 0.85, "assoc": 2.0, "facts": {"weapons_involved": 0.15},
    },
    "Neela Saanp Syndicate": {
        "alias": "NSS, Blue Cobra", "territory": "Bengaluru, Kolkata", "states": ["Karnataka", "West Bengal"],
        "threat_level": "high", "known_activities": "Online fraud call centres, phishing, mule accounts",
        "specialties": {"Cybercrime": 0.55, "Fraud": 0.30, "Money Laundering": 0.15},
        "age_shift": -3, "night": 0.15, "assoc": 7.0, "facts": {"tech_involvement": 0.25},
    },
    "Teen Talwar Gang": {
        "alias": "TTG, Three Swords", "territory": "Ahmedabad, Chennai", "states": ["Gujarat", "Tamil Nadu"],
        "threat_level": "critical", "known_activities": "Protection rackets, contract violence, illegal arms",
        "specialties": {"Extortion": 0.45, "Murder": 0.25, "Arms Trafficking": 0.30},
        "age_shift": 8, "night": 0.45, "assoc": 3.0, "facts": {"weapons_involved": 0.20},
    },
    "Patang Syndicate": {
        "alias": "The Kite Network", "territory": "Hyderabad, Ludhiana", "states": ["Telangana", "Punjab"],
        "threat_level": "high", "known_activities": "Trafficking of persons, kidnapping for ransom, extortion",
        "specialties": {"Human Trafficking": 0.45, "Kidnapping": 0.35, "Extortion": 0.20},
        "age_shift": 6, "night": 0.40, "assoc": 9.0, "facts": {"tech_involvement": 0.15},
    },
    "Kaali Billi Crew": {
        "alias": "KBC, Black Cats", "territory": "Bhopal, Gurugram", "states": ["Madhya Pradesh", "Haryana"],
        "threat_level": "medium", "known_activities": "Night burglaries, vehicle lifting, arson, vandalism",
        "specialties": {"Burglary": 0.35, "Car Theft": 0.25, "Vandalism": 0.20, "Arson": 0.20},
        "age_shift": -7, "night": 0.90, "assoc": 1.0, "facts": {"drug_involvement": 0.15},
    },
}
assert list(GANGS) == GANG_NAMES, "GANGS must match app.constants.GANG_NAMES"
assert set(CRIME_MIX) == set(CRIME_PROFILES) == set(CRIME_TYPES)

# Weights roughly following population, for the analysis slice only.
STATE_WEIGHTS = {
    "Uttar Pradesh": 16, "Maharashtra": 10, "Bihar": 9, "West Bengal": 7, "Madhya Pradesh": 6,
    "Rajasthan": 6, "Tamil Nadu": 6, "Karnataka": 5, "Gujarat": 5, "Telangana": 3, "Kerala": 3,
    "Delhi": 3, "Punjab": 2, "Haryana": 2,
}
SEVERITY = {
    "Murder": 1.0, "Human Trafficking": 1.0, "Arms Trafficking": 1.0, "Kidnapping": 0.8, "Drug Trafficking": 0.8,
    "Robbery": 0.75, "Assault": 0.7, "Extortion": 0.6, "Money Laundering": 0.55, "Fraud": 0.5, "Arson": 0.5,
    "Burglary": 0.4, "Car Theft": 0.35, "Cybercrime": 0.35, "Vandalism": 0.2,
}
NIGHT_HOURS = [20, 21, 22, 23, 0, 1, 2, 3, 4]


def _pick(rng: np.random.RandomState, weights: dict) -> str:
    names = list(weights)
    p = np.asarray([weights[n] for n in names], dtype=float)
    return str(names[rng.choice(len(names), p=p / p.sum())])


def generate_rows(n_samples: int = N_SAMPLES) -> list:
    rng = np.random.RandomState(SEED)
    span = (END - START).days
    rows = []
    for _ in range(n_samples):
        member = rng.rand() < GANG_MEMBER_SHARE
        gang = GANGS[_pick(rng, {name: 1 for name in GANGS})] if member else None
        if member and rng.rand() < SPECIALTY_SHARE:
            crime = _pick(rng, gang["specialties"])
        else:
            crime = _pick(rng, CRIME_MIX)
        weapons, drugs, money, tech, night, age_mu, assoc_mu, viol_mu = CRIME_PROFILES[crime]
        base = dict(zip(FACT_NAMES, (weapons, drugs, money, tech)))
        facts = {}
        for name in FACT_NAMES:
            p = base[name] + (gang["facts"].get(name, 0.0) if gang else 0.0)
            facts[name] = int(rng.rand() < min(p, 0.99))
        night_p = 0.6 * night + 0.4 * gang["night"] if gang else night
        hour = int(rng.choice(NIGHT_HOURS)) if rng.rand() < night_p else int(rng.randint(8, 20))
        age = int(np.clip(round(rng.normal(age_mu + (gang["age_shift"] if gang else 0), 6.5)), 16, 70))
        associates = int(min(rng.poisson(assoc_mu + (gang["assoc"] if gang else 0.0)), 40))
        violence = int(min(rng.poisson(viol_mu + 0.8 * member), 20))
        prior = int(min(rng.poisson(0.5 + 1.0 * member + 0.25 * violence + 0.04 * max(age - 20, 0)), 30))
        location_risk = round(float(rng.beta(2 + 3 * member + 2 * (viol_mu > 1.8), 4)), 3)
        incident = START + timedelta(days=int(rng.randint(span + 1)))
        state = str(rng.choice(gang["states"])) if gang else _pick(rng, STATE_WEIGHTS)

        logit = (-2.6 + 0.38 * min(prior, 8) - 0.045 * (age - 30) + 0.85 * member + 0.45 * facts["weapons_involved"]
                 + 0.35 * facts["drug_involvement"] + 0.06 * min(associates, 15) + 0.25 * min(violence, 6)
                 + 0.9 * SEVERITY[crime])
        reoffended = int(rng.rand() < 1.0 / (1.0 + np.exp(-logit)))

        gang_label = next(name for name, g in GANGS.items() if g is gang) if gang else "None"
        rows.append([prior, age, int(member), facts["weapons_involved"], facts["drug_involvement"],
                     facts["financial_motivation"], facts["tech_involvement"], violence, location_risk, hour,
                     associates, crime, gang_label, incident.isoformat(), state, reoffended])
    return rows


def write_dataset(rows: list) -> str:
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest = {
        "dataset_name": "AI-CRMS India Demonstration Crime Training Dataset",
        "dataset_version": "india-1.0",
        "dataset_type": "synthetic_demonstration",
        "generated_with_seed": SEED,
        "rows": len(rows),
        "feature_columns": FEATURE_COLUMNS,
        "target_columns": ["crime_type", "gang_label"],
        "optional_columns": ["incident_date", "slice_state", "reoffended_2y"],
        "sha256": digest,
        "source": ("Deterministic synthetic generator (app/ml/data/generate_india_dataset.py). Crime mix follows the "
                   "broad ordering of NCRB 'Crime in India' offence volumes (indicative shares, rare classes "
                   "floored); gangs are fictional. No real person, case or gang."),
        "label_definition": "Simulated: crime_type and gang_label from fictional gang/crime profiles; "
                            "reoffended_2y simulated from prior convictions, age, membership and violence.",
        "schema_version": "1.2",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return digest


if __name__ == "__main__":
    digest = write_dataset(generate_rows())
    print(f"Wrote {OUTPUT} ({N_SAMPLES} rows, sha256 {digest})")
