"""Build the model-input dict for a case and/or criminal record.

Shared by the prediction endpoint and the training-data exporter so that a
training row and a live prediction for the same case are built identically
(no train/serve skew). Only observed fields are included; unrecorded ones are
left out so they are reported as defaulted and imputed, never guessed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.constants import CASE_DETAIL_FIELDS
from app.ml.pipeline import CASE_INCIDENT_FEATURES


def model_input(criminal: Optional[Any] = None, case: Optional[Any] = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if criminal is not None:
        data = {
            "id": criminal.id,
            "first_name": criminal.first_name,
            "last_name": criminal.last_name,
            "prior_convictions": criminal.prior_convictions,
            "date_of_birth": str(criminal.date_of_birth) if criminal.date_of_birth else None,
            "crime_type": criminal.crime_type,
            "gang_id": criminal.gang_id,
            "is_wanted": criminal.is_wanted,
            "is_incarcerated": criminal.is_incarcerated,
            "known_associates": criminal.known_associates,
        }
    if case is not None:
        if criminal is None:
            data = {
                "crime_type": case.crime_type if case.crime_type not in ("Other", "Unclassified") else None,
                "prior_convictions": None,
            }
        # The incident timestamp is an observed case field. It can support the
        # time-of-day feature without inferring any feature from the target label.
        if case.incident_date is not None:
            data["incident_date"] = case.incident_date.isoformat()
        # Officer-recorded incident facts; unrecorded (NULL) fields stay absent
        # so feature_input_quality reports them as defaulted, not observed.
        for name in CASE_INCIDENT_FEATURES:
            value = getattr(case, name)
            if value is not None:
                data[name] = int(value)
        for name in CASE_DETAIL_FIELDS:
            value = getattr(case, name)
            if value:
                data[name] = value
    return data
