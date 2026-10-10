"""Offline place lookup for the incident map.

Case locations are free text such as "Dongri, Mumbai". This module resolves
them to approximate coordinates from a built-in gazetteer of Indian cities
and well-known localities, so the map works without sending case data to an
external geocoding service. Unknown places are reported as unmapped rather
than guessed.
"""
from __future__ import annotations

import hashlib
from typing import Optional, Tuple

# (latitude, longitude), rounded to ~1 km: enough for a city-level overview.
CITIES = {
    "mumbai": (19.076, 72.878), "new delhi": (28.614, 77.209), "delhi": (28.704, 77.102),
    "bengaluru": (12.972, 77.595), "bangalore": (12.972, 77.595), "hyderabad": (17.385, 78.487),
    "secunderabad": (17.440, 78.499), "chennai": (13.083, 80.270), "kolkata": (22.573, 88.364),
    "pune": (18.520, 73.857), "ahmedabad": (23.023, 72.571), "surat": (21.170, 72.831),
    "jaipur": (26.912, 75.787), "lucknow": (26.847, 80.947), "kanpur": (26.449, 80.332),
    "nagpur": (21.146, 79.088), "indore": (22.720, 75.858), "bhopal": (23.260, 77.413),
    "patna": (25.594, 85.138), "ludhiana": (30.901, 75.857), "chandigarh": (30.733, 76.779),
    "amritsar": (31.634, 74.872), "gurugram": (28.459, 77.027), "gurgaon": (28.459, 77.027),
    "noida": (28.535, 77.391), "ghaziabad": (28.669, 77.454), "faridabad": (28.408, 77.318),
    "kochi": (9.931, 76.267), "thiruvananthapuram": (8.524, 76.937), "coimbatore": (11.017, 76.956),
    "madurai": (9.925, 78.120), "visakhapatnam": (17.687, 83.218), "vijayawada": (16.506, 80.648),
    "guwahati": (26.144, 91.736), "bhubaneswar": (20.296, 85.825), "ranchi": (23.344, 85.310),
    "raipur": (21.251, 81.630), "dehradun": (30.317, 78.032), "srinagar": (34.084, 74.797),
    "jammu": (32.727, 74.857), "varanasi": (25.318, 82.974), "agra": (27.177, 78.008),
    "vadodara": (22.307, 73.181), "rajkot": (22.303, 70.802), "nashik": (19.998, 73.790),
    "mysuru": (12.296, 76.639), "mangaluru": (12.914, 74.856), "goa": (15.491, 73.828),
    "panaji": (15.491, 73.828), "shimla": (31.105, 77.173),
}

# Localities used in the demo data and other commonly reported areas.
LOCALITIES = {
    ("dongri", "mumbai"): (18.962, 72.836), ("andheri east", "mumbai"): (19.116, 72.870),
    ("zaveri bazaar", "mumbai"): (18.950, 72.832), ("dharavi", "mumbai"): (19.041, 72.855),
    ("mahipalpur", "new delhi"): (28.545, 77.124), ("karol bagh", "new delhi"): (28.652, 77.190),
    ("electronic city", "bengaluru"): (12.845, 77.660), ("koramangala", "bengaluru"): (12.935, 77.625),
    ("secunderabad", "hyderabad"): (17.440, 78.499), ("banjara hills", "hyderabad"): (17.416, 78.438),
    ("naroda", "ahmedabad"): (23.068, 72.653), ("mp nagar", "bhopal"): (23.233, 77.434),
    ("ernakulam", "kochi"): (9.982, 76.300), ("park street", "kolkata"): (22.553, 88.352),
    ("t. nagar", "chennai"): (13.042, 80.234), ("t nagar", "chennai"): (13.042, 80.234),
    ("sector 29", "gurugram"): (28.468, 77.064), ("johari bazaar", "jaipur"): (26.920, 75.827),
    ("model town", "ludhiana"): (30.888, 75.837),
}


def _norm(part: str) -> str:
    return " ".join(part.strip().lower().split())


def _jitter(seed: str, spread: float) -> Tuple[float, float]:
    """Small, stable offset so several cases in one place don't hide each other."""
    digest = hashlib.sha256(seed.encode()).digest()
    return ((digest[0] / 255 - 0.5) * spread, (digest[1] / 255 - 0.5) * spread)


def resolve(location: Optional[str], seed: str = "") -> Optional[dict]:
    """Return ``{"lat", "lng", "city", "precision"}`` for a free-text location, or None."""
    if not location:
        return None
    parts = [_norm(p) for p in location.replace(";", ",").split(",") if p.strip()]
    if not parts:
        return None
    for i in range(len(parts) - 1):
        point = LOCALITIES.get((parts[i], parts[i + 1]))
        if point:
            d_lat, d_lng = _jitter(seed, 0.004)
            return {"lat": round(point[0] + d_lat, 5), "lng": round(point[1] + d_lng, 5),
                    "city": parts[i + 1].title(), "precision": "locality"}
    for part in reversed(parts):
        point = CITIES.get(part)
        if point:
            d_lat, d_lng = _jitter(seed, 0.04)
            return {"lat": round(point[0] + d_lat, 5), "lng": round(point[1] + d_lng, 5),
                    "city": part.title(), "precision": "city"}
    return None
