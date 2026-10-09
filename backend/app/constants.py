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

# Fictional demonstration gangs (see app/ml/data/generate_india_dataset.py).
# The gang model's classes are these names plus "None".
GANG_NAMES = [
    "Kaala Bichhoo Gang", "Lal Toofan Crew", "Neela Saanp Syndicate",
    "Teen Talwar Gang", "Patang Syndicate", "Kaali Billi Crew",
]

# Incident details recorded on a case (as in FIR "place of occurrence",
# "property/target" and modus-operandi fields). Keys are stored on the case and
# become one-hot AI model inputs; values are the labels shown to officers.
LOCATION_TYPES = {
    "residence": "Home / residence",
    "business": "Shop, office or business",
    "public_place": "Street or public place",
    "transport": "Vehicle, transport or highway",
    "financial": "Bank, ATM or financial office",
    "online": "Online or by phone",
}
TARGET_TYPES = {
    "person": "A person",
    "property": "Goods or property",
    "vehicle": "A vehicle",
    "money": "Money or financial assets",
    "data": "Data, accounts or identity",
    "contraband": "Drugs, arms or contraband",
}
MODUS_OPERANDI = {
    "forced_entry": "Forced entry or break-in",
    "armed_threat": "Threat with a weapon",
    "physical_violence": "Physical violence",
    "deception": "Deception, cheating or impersonation",
    "cyber_intrusion": "Hacking, phishing or digital intrusion",
    "smuggling": "Concealed transport or smuggling",
    "abduction": "Taking or holding a person",
    "fire_damage": "Fire or deliberate damage",
    "intimidation": "Threats or coercion",
}
# Case field -> (vocabulary, prefix of its one-hot model feature names).
CASE_DETAIL_FIELDS = {
    "location_type": (LOCATION_TYPES, "location"),
    "target_type": (TARGET_TYPES, "target"),
    "modus_operandi": (MODUS_OPERANDI, "method"),
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
