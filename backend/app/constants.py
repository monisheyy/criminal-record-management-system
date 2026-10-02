"""Domain vocabularies shared by validation, the ML pipeline and the UI."""

CRIME_TYPES = [
    "Robbery", "Assault", "Murder", "Drug Trafficking", "Burglary",
    "Cybercrime", "Fraud", "Kidnapping", "Arms Trafficking", "Extortion",
    "Human Trafficking", "Car Theft", "Vandalism", "Arson", "Money Laundering",
]

CRIME_CATEGORIES = {
    "Robbery": "Violent", "Assault": "Violent", "Murder": "Violent",
    "Kidnapping": "Violent", "Drug Trafficking": "Narcotics",
    "Arms Trafficking": "Weapons", "Human Trafficking": "Organized Crime",
    "Fraud": "Financial", "Money Laundering": "Financial", "Extortion": "Financial",
    "Burglary": "Property", "Car Theft": "Property", "Vandalism": "Property",
    "Arson": "Property", "Cybercrime": "Technology",
}

# Case files may be opened before the offence is classified.
CASE_CRIME_TYPES = CRIME_TYPES + ["Other", "Unclassified"]

GENDERS = ["Male", "Female", "Other", "Unknown"]

CASE_ROLES = ["suspect", "accused", "primary_offender", "accomplice", "convicted", "witness"]

EVIDENCE_TYPES = ["physical", "digital", "forensic", "biological", "document", "weapon", "witness", "other"]

HISTORY_EVENT_TYPES = [
    "arrest", "charge", "conviction", "acquittal", "release", "parole",
    "warrant_issued", "warrant_cleared", "bail_granted", "wanted_notice", "sighting",
    "associate_link", "record_created", "record_updated", "record_corrected", "note",
]

AI_ADVISORY_NOTICE = (
    "Unverified decision-support output from a prototype model. It is not evidence, "
    "not a finding of guilt or dangerousness, and must not be the sole basis for any action. "
    "A qualified human reviewer must assess it against the underlying record."
)
