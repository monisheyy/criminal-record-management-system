"""Best accuracy any model can reach on the bundled synthetic dataset.

Run from backend/:
    python -m app.ml.data.accuracy_ceiling

The demo data is generated at random from known profiles (see
generate_india_dataset.py), so different crimes and gangs share the same
inputs. This computes the Bayes-optimal accuracy on the locked holdout (the
newest 20% of incidents): for every row, the exact probability of each label
under the generator, then the most likely label. No model trained on these
inputs can do better on average. It applies to the bundled demo data only.
"""
from __future__ import annotations

import csv
from typing import Dict, Optional

import numpy as np
from scipy.stats import beta, norm, poisson
from sklearn.metrics import roc_auc_score

from app.ml.data import generate_india_dataset as G
from app.ml.pipeline import TEST_SIZE, TOP_K_SUGGESTIONS

CRIMES = list(G.CRIME_PROFILES)
GANGS = [None] + list(G.GANGS)
_MIX = np.array([G.CRIME_MIX[c] for c in CRIMES], dtype=float)
_MIX /= _MIX.sum()


def _crime_prior(gang: Optional[str]) -> np.ndarray:
    if gang is None:
        return _MIX
    specialties = G.GANGS[gang]["specialties"]
    weights = np.array([specialties.get(c, 0.0) for c in CRIMES], dtype=float)
    return G.SPECIALTY_SHARE * weights / weights.sum() + (1 - G.SPECIALTY_SHARE) * _MIX


def _capped_poisson(k: int, lam: float, cap: int) -> float:
    return float(poisson.sf(cap - 1, lam)) if k >= cap else float(poisson.pmf(k, lam))


def _likelihood(row: Dict[str, str], gang: Optional[str], crime: str, use_membership: bool) -> float:
    profile = G.GANGS[gang] if gang else None
    member = int(gang is not None)
    if use_membership and int(row["is_gang_member"]) != member:
        return 0.0
    weapons, drugs, money, tech, night, age_mu, assoc_mu, viol_mu = G.CRIME_PROFILES[crime]
    value = 1.0
    for name, base in zip(G.FACT_NAMES, (weapons, drugs, money, tech)):
        p = min(base + (profile["facts"].get(name, 0.0) if profile else 0.0), 0.99)
        value *= p if int(row[name]) else 1 - p
    night_p = 0.6 * night + 0.4 * profile["night"] if profile else night
    value *= night_p / len(G.NIGHT_HOURS) if int(row["time_of_crime"]) in G.NIGHT_HOURS else (1 - night_p) / 12
    age, mu = int(row["age"]), age_mu + (profile["age_shift"] if profile else 0)
    low, high = (-np.inf if age <= 16 else age - 0.5), (np.inf if age >= 70 else age + 0.5)
    value *= norm.cdf(high, mu, 6.5) - norm.cdf(low, mu, 6.5)
    value *= _capped_poisson(int(row["associates_count"]), assoc_mu + (profile["assoc"] if profile else 0.0), 40)
    violence = int(row["violence_history"])
    value *= _capped_poisson(violence, viol_mu + 0.8 * member, 20)
    value *= _capped_poisson(int(row["prior_convictions"]), 0.5 + member + 0.25 * violence + 0.04 * max(age - 20, 0), 30)
    value *= beta.pdf(max(float(row["location_risk"]), 1e-6), 2 + 3 * member + 2 * (viol_mu > 1.8), 4)
    return value


def _posterior(row: Dict[str, str], use_membership: bool) -> np.ndarray:
    joint = np.zeros((len(GANGS), len(CRIMES)))
    for i, gang in enumerate(GANGS):
        gang_prior = 1 - G.GANG_MEMBER_SHARE if gang is None else G.GANG_MEMBER_SHARE / len(G.GANGS)
        prior = _crime_prior(gang)
        for j, crime in enumerate(CRIMES):
            joint[i, j] = gang_prior * prior[j] * _likelihood(row, gang, crime, use_membership)
    return joint / joint.sum()


def holdout_rows() -> list:
    with G.OUTPUT.open(newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda r: r["incident_date"])
    return rows[int(round(len(rows) * (1 - TEST_SIZE))):]


def ceilings() -> Dict[str, float]:
    rows = holdout_rows()
    crime_top1 = crime_topk = gang_top1 = 0
    risk_logits, outcomes = [], []
    for row in rows:
        # The crime model sees is_gang_member; the gang model does not.
        crime_p = _posterior(row, use_membership=True).sum(axis=0)
        ranked = [CRIMES[i] for i in np.argsort(-crime_p)]
        crime_top1 += ranked[0] == row["crime_type"]
        crime_topk += row["crime_type"] in ranked[:TOP_K_SUGGESTIONS]
        gang_p = _posterior(row, use_membership=False).sum(axis=1)
        gang_top1 += (GANGS[int(gang_p.argmax())] or "None") == row["gang_label"]
        f = {k: float(row[k]) for k in G.FEATURE_COLUMNS}
        risk_logits.append(0.38 * min(f["prior_convictions"], 8) - 0.045 * (f["age"] - 30) + 0.85 * f["is_gang_member"]
                           + 0.45 * f["weapons_involved"] + 0.35 * f["drug_involvement"]
                           + 0.06 * min(f["associates_count"], 15) + 0.25 * min(f["violence_history"], 6)
                           + 0.9 * G.SEVERITY[row["crime_type"]])
        outcomes.append(int(row["reoffended_2y"]))
    n = len(rows)
    return {
        "holdout_rows": n,
        "crime_accuracy": crime_top1 / n,
        f"crime_top_{TOP_K_SUGGESTIONS}_accuracy": crime_topk / n,
        "gang_accuracy": gang_top1 / n,
        # Uses the true crime type, which the danger-score model does not see: an upper bound.
        "danger_score_roc_auc": float(roc_auc_score(outcomes, risk_logits)),
    }


if __name__ == "__main__":
    for name, value in ceilings().items():
        print(f"{name:<28}{value:.3f}" if isinstance(value, float) else f"{name:<28}{value}")
