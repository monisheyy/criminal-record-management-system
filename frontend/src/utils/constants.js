// Vocabularies mirrored from backend/app/constants.py. The API validates them;
// keeping the same lists here lets forms offer only values that will be accepted.

export const CRIME_TYPES = [
  'Robbery', 'Assault', 'Murder', 'Drug Trafficking', 'Burglary',
  'Cybercrime', 'Fraud', 'Kidnapping', 'Arms Trafficking', 'Extortion',
  'Human Trafficking', 'Car Theft', 'Vandalism', 'Arson', 'Money Laundering',
];

export const CASE_CRIME_TYPES = [...CRIME_TYPES, 'Other', 'Unclassified'];

export const GENDERS = ['Male', 'Female', 'Other', 'Unknown'];

export const CASE_PRIORITIES = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

// Officer-recorded incident facts; keys match the backend Case columns and AI model features.
export const CASE_INCIDENT_FACTS = [
  { key: 'weapons_involved', label: 'Weapon involved' },
  { key: 'drug_involvement', label: 'Drugs involved' },
  { key: 'financial_motivation', label: 'Financial motive' },
  { key: 'tech_involvement', label: 'Technology used' },
];

export const CASE_STATUSES = [
  { value: 'open', label: 'Open' },
  { value: 'under_investigation', label: 'Under investigation' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
];

// Mirrors STATUS_TRANSITIONS in backend/app/routers/cases.py (non-admin users).
export const CASE_STATUS_TRANSITIONS = {
  open: ['under_investigation', 'closed'],
  under_investigation: ['open', 'closed'],
  closed: ['under_investigation', 'archived'],
  archived: [],
};

export const CASE_ROLES = [
  { value: 'suspect', label: 'Suspect' },
  { value: 'accused', label: 'Accused' },
  { value: 'primary_offender', label: 'Primary offender' },
  { value: 'accomplice', label: 'Accomplice' },
  { value: 'convicted', label: 'Convicted' },
  { value: 'witness', label: 'Witness' },
];

export const EVIDENCE_TYPES = [
  { value: 'physical', label: 'Physical' },
  { value: 'digital', label: 'Digital' },
  { value: 'forensic', label: 'Forensic' },
  { value: 'biological', label: 'Biological' },
  { value: 'document', label: 'Document' },
  { value: 'weapon', label: 'Weapon' },
  { value: 'witness', label: 'Witness' },
  { value: 'other', label: 'Other' },
];

export const EVIDENCE_STATUSES = [
  { value: 'collected', label: 'Collected' },
  { value: 'stored', label: 'Stored' },
  { value: 'analyzed', label: 'Analyzed' },
  { value: 'submitted_to_court', label: 'Submitted to court' },
  { value: 'released', label: 'Released' },
];

export const VICTIM_STATUSES = [
  { value: 'alive', label: 'Alive' },
  { value: 'hospitalized', label: 'Hospitalized' },
  { value: 'deceased', label: 'Deceased' },
];

export const THREAT_LEVELS = ['low', 'medium', 'high', 'critical'];

export const PASSWORD_MIN_LENGTH = 10;

export const ROLE_LABELS = {
  admin: 'Administrator',
  investigating_officer: 'Investigating Officer',
  record_clerk: 'Record Clerk',
};
