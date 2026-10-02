"""Request/response contracts.

Design rule: *input* schemas are strict (lengths match the database columns,
vocabularies are enumerated, URLs/phones/hashes are pattern-checked, dates are
range-checked) so bad data is rejected with a 422 before it reaches the
database. *Output* schemas stay permissive so that legacy rows written before
these rules existed can still be read.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator,
)

from app.constants import (
    CASE_CRIME_TYPES, CASE_ROLES, CRIME_TYPES, EVIDENCE_TYPES, GENDERS, HISTORY_EVENT_TYPES,
)


# ── Reusable constrained types ───────────────────────────────────────────────
def Str(max_length: int, min_length: int = 0, pattern: Optional[str] = None):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length,
                                            max_length=max_length, pattern=pattern)]


# Letters (any script), spaces, apostrophes, hyphens and dots. Also keeps
# markup characters out of generated PDF reports.
Name = Str(50, 1, r"^[^\W\d_](?:[^\W\d_]|[ .'\-])*$")
ShortText = Str(200)
LongText = Str(10_000)
Phone = Str(20, 5, r"^[0-9+()\-\s.]{5,20}$")
Sha256Hex = Str(64, 64, r"^[0-9a-fA-F]{64}$")
Username = Str(50, 3, r"^[A-Za-z0-9_.\-]{3,50}$")


def _check_url(value: Optional[str]) -> Optional[str]:
    """Only http(s) URLs or server-relative paths: blocks javascript:/data: URLs
    that would execute when rendered as a link or image source."""
    if value is None or value == "":
        return None
    value = value.strip()
    if len(value) > 500:
        raise ValueError("URL must be at most 500 characters")
    if value.startswith("/") and not value.startswith("//"):
        return value
    if value.lower().startswith(("https://", "http://")):
        return value
    raise ValueError("Only http(s) URLs or server-relative paths are allowed")


def _not_future(value: Optional[datetime], field_name: str) -> Optional[datetime]:
    if value is None:
        return value
    compare = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if compare > datetime.now(timezone.utc):
        raise ValueError(f"{field_name} cannot be in the future")
    return value


def _in_vocabulary(value: Optional[str], allowed: List[str], field_name: str) -> Optional[str]:
    if value is None or value == "":
        return None
    for option in allowed:
        if value.strip().lower() == option.lower():
            return option  # normalise casing to the canonical value
    raise ValueError(f"{field_name} must be one of: {', '.join(allowed)}")


# ── Enums ───────────────────────────────────────────────────────────────────
class UserRole(str, Enum):
    admin = "admin"
    investigating_officer = "investigating_officer"
    record_clerk = "record_clerk"


class CaseStatus(str, Enum):
    open = "open"
    under_investigation = "under_investigation"
    closed = "closed"
    archived = "archived"


class PredictionStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    overridden = "overridden"


class ThreatLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CasePriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class EvidenceStatus(str, Enum):
    collected = "collected"
    stored = "stored"
    analyzed = "analyzed"
    submitted_to_court = "submitted_to_court"
    released = "released"


class VictimStatus(str, Enum):
    alive = "alive"
    deceased = "deceased"
    hospitalized = "hospitalized"


# ── Auth Schemas ─────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_at: Optional[datetime] = None
    user: "UserOut"


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── User Schemas ─────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username: str
    email: str
    full_name: str
    role: UserRole
    badge_number: Optional[str] = None
    department: Optional[str] = None


class UserCreate(BaseModel):
    username: Username
    email: EmailStr
    full_name: Str(100, 2)
    role: UserRole
    badge_number: Optional[Str(20)] = None
    department: Optional[Str(100)] = None
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[Str(100, 2)] = None
    role: Optional[UserRole] = None
    badge_number: Optional[Str(20)] = None
    department: Optional[Str(100)] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    must_change_password: Optional[bool] = None
    unlock: Optional[bool] = Field(None, description="Clear a temporary login lockout")


class UserOut(UserBase):
    id: int
    is_active: bool
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSummary(BaseModel):
    """Minimal directory entry for assignment pickers (no contact details)."""
    id: int
    full_name: str
    badge_number: Optional[str] = None
    department: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── Gang Schemas ─────────────────────────────────────────────────────────────
class GangBase(BaseModel):
    name: str
    alias: Optional[str] = None
    territory: Optional[str] = None
    threat_level: Optional[str] = "medium"
    known_activities: Optional[str] = None
    member_count: Optional[int] = 0
    is_active: Optional[bool] = True


class GangCreate(BaseModel):
    name: Str(100, 2)
    alias: Optional[Str(200)] = None
    territory: Optional[Str(200)] = None
    threat_level: ThreatLevel = ThreatLevel.medium
    known_activities: Optional[Str(5000)] = None
    member_count: int = Field(0, ge=0, le=100_000)
    is_active: bool = True


class GangUpdate(BaseModel):
    name: Optional[Str(100, 2)] = None
    alias: Optional[Str(200)] = None
    territory: Optional[Str(200)] = None
    threat_level: Optional[ThreatLevel] = None
    known_activities: Optional[Str(5000)] = None
    member_count: Optional[int] = Field(None, ge=0, le=100_000)
    is_active: Optional[bool] = None


class GangOut(GangBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Criminal Schemas ─────────────────────────────────────────────────────────
class CriminalBase(BaseModel):
    """Permissive read shape (legacy rows may predate validation rules)."""
    first_name: str
    last_name: str
    alias: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    occupation: Optional[str] = None
    photo_url: Optional[str] = None
    fingerprint_id: Optional[str] = None
    crime_type: Optional[str] = None
    crime_category: Optional[str] = None
    prior_convictions: Optional[int] = 0
    modus_operandi: Optional[str] = None
    known_associates: Optional[str] = None
    gang_id: Optional[int] = None
    gang_rank: Optional[str] = None
    is_wanted: Optional[bool] = False
    is_incarcerated: Optional[bool] = False
    threat_level: Optional[str] = "low"


class _CriminalWriteFields(BaseModel):
    alias: Optional[Str(200)] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    nationality: Optional[Str(50)] = None
    address: Optional[Str(1000)] = None
    phone: Optional[Phone] = None
    email: Optional[EmailStr] = None
    occupation: Optional[Str(100)] = None
    photo_url: Optional[str] = None
    fingerprint_id: Optional[Str(100)] = None
    crime_type: Optional[str] = None
    crime_category: Optional[Str(50)] = None
    prior_convictions: Optional[int] = Field(None, ge=0, le=100)
    modus_operandi: Optional[Str(5000)] = None
    known_associates: Optional[Str(2000)] = None
    gang_id: Optional[int] = Field(None, ge=1)
    gang_rank: Optional[Str(50)] = None
    is_wanted: Optional[bool] = None
    is_incarcerated: Optional[bool] = None
    threat_level: Optional[ThreatLevel] = None

    @field_validator("photo_url")
    @classmethod
    def _url(cls, value):
        return _check_url(value)

    @field_validator("gender")
    @classmethod
    def _gender(cls, value):
        return _in_vocabulary(value, GENDERS, "gender")

    @field_validator("crime_type")
    @classmethod
    def _crime_type(cls, value):
        return _in_vocabulary(value, CRIME_TYPES, "crime_type")

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, value):
        value = _not_future(value, "date_of_birth")
        if value is not None and value.year < 1900:
            raise ValueError("date_of_birth is implausibly old")
        return value

    @field_validator("phone", "email", "address", "nationality", "occupation", "fingerprint_id",
                     "crime_category", "modus_operandi", "known_associates", "gang_rank", "alias",
                     mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        return None if isinstance(value, str) and value.strip() == "" else value


class CriminalCreate(_CriminalWriteFields):
    first_name: Name
    last_name: Name
    prior_convictions: int = Field(0, ge=0, le=100)
    is_wanted: bool = False
    is_incarcerated: bool = False
    threat_level: ThreatLevel = ThreatLevel.low
    acknowledge_possible_duplicate: bool = Field(
        False, description="Set true to create the record even though a likely duplicate exists"
    )


class CriminalUpdate(_CriminalWriteFields):
    first_name: Optional[Name] = None
    last_name: Optional[Name] = None
    correction_reason: Optional[Str(500)] = Field(
        None, description="Why the record is being changed; stored in the record history"
    )


class CriminalHistoryCreate(BaseModel):
    event_type: str
    description: Str(2000, 3)
    date: Optional[datetime] = None
    location: Optional[Str(200)] = None
    case_reference: Optional[Str(50)] = None

    @field_validator("event_type")
    @classmethod
    def _event_type(cls, value):
        return _in_vocabulary(value, HISTORY_EVENT_TYPES, "event_type")

    @field_validator("date")
    @classmethod
    def _date(cls, value):
        return _not_future(value, "date")


class CriminalHistoryItem(BaseModel):
    id: int
    event_type: str
    description: Optional[str]
    date: Optional[datetime]
    location: Optional[str]
    case_reference: Optional[str]
    recorded_by: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CriminalOut(CriminalBase):
    id: int
    crn: str
    risk_score: float
    created_at: datetime
    updated_at: Optional[datetime]
    gang: Optional[GangOut] = None

    model_config = ConfigDict(from_attributes=True)


class DuplicateCheckResult(BaseModel):
    has_duplicates: bool
    duplicates: List[CriminalOut]
    match_score: float


# ── Case / FIR Schemas ───────────────────────────────────────────────────────
class CaseBase(BaseModel):
    """Permissive read shape."""
    title: str
    description: Optional[str] = None
    crime_type: Optional[str] = None
    crime_category: Optional[str] = None
    location: Optional[str] = None
    incident_date: Optional[datetime] = None
    priority: Optional[str] = "normal"
    fir_number: Optional[str] = None
    fir_date: Optional[datetime] = None
    fir_filed_by: Optional[str] = None
    fir_station: Optional[str] = None
    complainant_name: Optional[str] = None
    complainant_contact: Optional[str] = None
    assigned_officer_id: Optional[int] = None


class _CaseWriteFields(BaseModel):
    description: Optional[LongText] = None
    crime_type: Optional[str] = None
    crime_category: Optional[Str(50)] = None
    location: Optional[Str(200)] = None
    incident_date: Optional[datetime] = None
    priority: Optional[CasePriority] = None
    fir_number: Optional[Str(30, 3, r"^[A-Za-z0-9/\-_.]{3,30}$")] = None
    fir_date: Optional[datetime] = None
    fir_filed_by: Optional[Str(100)] = None
    fir_station: Optional[Str(100)] = None
    complainant_name: Optional[Str(100)] = None
    complainant_contact: Optional[Phone] = None
    assigned_officer_id: Optional[int] = Field(None, ge=1)

    @field_validator("crime_type")
    @classmethod
    def _crime_type(cls, value):
        return _in_vocabulary(value, CASE_CRIME_TYPES, "crime_type")

    @field_validator("incident_date", "fir_date")
    @classmethod
    def _dates(cls, value, info):
        return _not_future(value, info.field_name)

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, value):
        # Accept "High"/"HIGH" and the common synonym "medium" from older clients.
        if isinstance(value, str):
            value = value.strip().lower()
            return "normal" if value == "medium" else value
        return value

    @field_validator("fir_number", "complainant_contact", "location", "fir_filed_by", "fir_station",
                     "complainant_name", "crime_category", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        return None if isinstance(value, str) and value.strip() == "" else value

    @model_validator(mode="after")
    def _fir_after_incident(self):
        if self.incident_date and self.fir_date:
            incident = self.incident_date if self.incident_date.tzinfo else self.incident_date.replace(tzinfo=timezone.utc)
            fir = self.fir_date if self.fir_date.tzinfo else self.fir_date.replace(tzinfo=timezone.utc)
            if fir < incident:
                raise ValueError("fir_date cannot be earlier than incident_date")
        return self


class CaseCreate(_CaseWriteFields):
    title: Str(200, 3)
    priority: CasePriority = CasePriority.normal
    criminal_ids: List[int] = Field(default_factory=list, max_length=50)


class CaseUpdate(_CaseWriteFields):
    title: Optional[Str(200, 3)] = None
    status: Optional[CaseStatus] = None
    criminal_ids: Optional[List[int]] = Field(None, max_length=50)
    status_reason: Optional[Str(500)] = None


class CaseCriminalLink(BaseModel):
    criminal_id: int = Field(..., ge=1)
    role: str = "suspect"

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, value):
        normalised = (value or "suspect").strip().lower().replace(" ", "_")
        if normalised not in CASE_ROLES:
            raise ValueError(f"role must be one of: {', '.join(CASE_ROLES)}")
        return normalised


class CaseAssignment(BaseModel):
    officer_id: int = Field(..., ge=1)


class CaseCriminalOut(BaseModel):
    id: int
    criminal_id: int
    role: Optional[str]
    criminal: CriminalOut

    model_config = ConfigDict(from_attributes=True)


class EvidenceOut(BaseModel):
    id: int
    evidence_number: str
    type: Optional[str]
    description: Optional[str]
    location_found: Optional[str]
    collected_by: Optional[str]
    collected_at: Optional[datetime]
    status: str
    chain_of_custody: Optional[str]
    file_url: Optional[str]
    file_sha256: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VictimOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    age: Optional[int]
    gender: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    injury_description: Optional[str]
    status: str
    statement: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseOut(CaseBase):
    id: int
    case_number: str
    status: CaseStatus
    created_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime] = None
    assigned_officer: Optional[UserSummary] = None
    criminals: List[CaseCriminalOut] = []
    evidence: List[EvidenceOut] = []
    victims: List[VictimOut] = []

    model_config = ConfigDict(from_attributes=True)


class CaseListItem(CaseBase):
    """Lightweight list row: avoids serialising every linked record per case."""
    id: int
    case_number: str
    status: CaseStatus
    created_at: datetime
    updated_at: Optional[datetime]
    assigned_officer: Optional[UserSummary] = None

    model_config = ConfigDict(from_attributes=True)


# ── Evidence & Victim Schemas ────────────────────────────────────────────────
class EvidenceCreate(BaseModel):
    type: Optional[str] = None
    description: Str(5000, 3)
    location_found: Optional[Str(200)] = None
    collected_by: Optional[Str(100)] = None
    collected_at: Optional[datetime] = None
    chain_of_custody: Optional[Str(5000)] = None
    file_url: Optional[str] = None
    file_sha256: Optional[Sha256Hex] = None
    status: EvidenceStatus = EvidenceStatus.collected

    @field_validator("type")
    @classmethod
    def _type(cls, value):
        return _in_vocabulary(value, EVIDENCE_TYPES, "type")

    @field_validator("file_url")
    @classmethod
    def _url(cls, value):
        return _check_url(value)

    @field_validator("collected_at")
    @classmethod
    def _collected(cls, value):
        return _not_future(value, "collected_at")

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("file_sha256", mode="before")
    @classmethod
    def _hash(cls, value):
        return None if isinstance(value, str) and value.strip() == "" else value


class EvidenceUpdate(BaseModel):
    type: Optional[str] = None
    description: Optional[Str(5000, 3)] = None
    location_found: Optional[Str(200)] = None
    collected_by: Optional[Str(100)] = None
    collected_at: Optional[datetime] = None
    status: Optional[EvidenceStatus] = None
    custody_note: Optional[Str(1000, 3)] = Field(
        None, description="Appended (never overwritten) to the chain-of-custody log"
    )

    @field_validator("type")
    @classmethod
    def _type(cls, value):
        return _in_vocabulary(value, EVIDENCE_TYPES, "type")

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class VictimCreate(BaseModel):
    first_name: Name
    last_name: Name
    age: Optional[int] = Field(None, ge=0, le=130)
    gender: Optional[str] = None
    address: Optional[Str(1000)] = None
    phone: Optional[Phone] = None
    injury_description: Optional[Str(5000)] = None
    status: VictimStatus = VictimStatus.alive
    statement: Optional[Str(10_000)] = None

    @field_validator("gender")
    @classmethod
    def _gender(cls, value):
        return _in_vocabulary(value, GENDERS, "gender")

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("phone", "address", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        return None if isinstance(value, str) and value.strip() == "" else value


# ── AI Prediction Schemas ────────────────────────────────────────────────────
class PredictionRequest(BaseModel):
    criminal_id: Optional[int] = Field(None, ge=1)
    case_id: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def _needs_subject(self):
        if self.criminal_id is None and self.case_id is None:
            raise ValueError("Provide criminal_id and/or case_id")
        return self


class AIPredictionReviewOut(BaseModel):
    id: int
    reviewer_id: Optional[int]
    reviewer_username: Optional[str]
    previous_status: Optional[str]
    decision: str
    remarks: str
    override_crime_type: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIPredictionOut(BaseModel):
    id: int
    criminal_id: Optional[int]
    case_id: Optional[int]
    predicted_crime_type: Optional[str]
    crime_type_confidence: float = Field(description="Model score in [0, 1]; not a calibrated probability")
    gang_affiliation_probability: float = Field(description="Model score in [0, 1]")
    predicted_gang_id: Optional[int]
    risk_score: float = Field(description="Prototype score in [1, 100]")
    risk_level: str
    confidence_overall: float
    similar_criminals: Optional[Any]
    similar_cases: Optional[Any]
    input_features: Optional[Any]
    review_status: PredictionStatus
    reviewed_by_id: Optional[int]
    reviewed_at: Optional[datetime]
    officer_remarks: Optional[str]
    override_crime_type: Optional[str]
    model_version: str
    created_at: datetime
    criminal: Optional[CriminalOut] = None
    reviews: List[AIPredictionReviewOut] = []
    advisory_notice: str = ""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class PredictionReview(BaseModel):
    status: Literal["confirmed", "rejected", "overridden"]
    remarks: Str(2000, 10) = Field(..., description="Reviewer's reasoning; required for every decision")
    override_crime_type: Optional[str] = None

    @field_validator("override_crime_type")
    @classmethod
    def _override(cls, value):
        return _in_vocabulary(value, CRIME_TYPES, "override_crime_type")

    @model_validator(mode="after")
    def _override_consistency(self):
        if self.status == "overridden" and not self.override_crime_type:
            raise ValueError("override_crime_type is required when overriding a prediction")
        if self.status != "overridden" and self.override_crime_type:
            raise ValueError("override_crime_type is only allowed when status is 'overridden'")
        return self


# ── Notification Schemas ─────────────────────────────────────────────────────
class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    related_criminal_id: Optional[int]
    related_case_id: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Audit Log Schemas ────────────────────────────────────────────────────────
class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str]
    role: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    details: Optional[Any]
    status: str
    reason: Optional[str]
    ip_address: Optional[str]
    request_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── ML Model Schemas ─────────────────────────────────────────────────────────
class MLModelOut(BaseModel):
    id: int
    version: str
    model_type: str
    accuracy: float
    precision_score: float
    recall_score: float
    f1_score: float
    training_samples: int
    feature_importances: Optional[Any]
    evaluation_metadata: Optional[Any]
    dataset_version: Optional[str]
    evaluation_method: Optional[str]
    trained_at: datetime
    is_active: bool
    activated_at: Optional[datetime] = None
    activated_by_id: Optional[int] = None
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ModelActivationRequest(BaseModel):
    justification: Str(2000, 20) = Field(..., description="Documented reason for promoting this candidate")


class ModelRollbackRequest(BaseModel):
    justification: Str(2000, 20)


# ── Dashboard Schemas ────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_criminals: int
    total_cases: int
    open_cases: int
    high_risk_criminals: int
    pending_reviews: int
    unread_alerts: int
    cases_by_status: Dict[str, int]
    crimes_by_type: Dict[str, int]
    monthly_cases: List[Dict[str, Any]]
    officer_workload: List[Dict[str, Any]]
    prediction_accuracy: float = Field(
        description="DEPRECATED name: share of reviewed predictions that reviewers confirmed. "
                    "This is a reviewer agreement rate, not model accuracy."
    )
    reviewer_agreement_rate: float = 0.0
    reviewed_predictions: int = 0


# ── System Setting Schemas ───────────────────────────────────────────────────
class SystemSettingBase(BaseModel):
    value: str
    description: Optional[str] = None


class SystemSettingUpdate(BaseModel):
    value: Str(200, 0)
    description: Optional[Str(2000)] = None


class SystemSettingOut(SystemSettingBase):
    key: str
    updated_at: Optional[datetime]
    updated_by_id: Optional[int]

    model_config = ConfigDict(from_attributes=True)


# ── Intelligence Network Schemas ────────────────────────────────────────────
class NetworkNode(BaseModel):
    id: str
    type: str
    label: str
    record_id: int
    route: Optional[str] = None
    crn: Optional[str] = None
    crime_type: Optional[str] = None
    risk_score: Optional[float] = None
    title: Optional[str] = None
    status: Optional[str] = None
    threat_level: Optional[str] = None
    member_count: Optional[int] = None
    username: Optional[str] = None
    badge_number: Optional[str] = None


class NetworkEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    case_id: Optional[int] = None
    case_number: Optional[str] = None
    gang_id: Optional[int] = None


class NetworkMetadata(BaseModel):
    criminal_id: Optional[int] = None
    case_id: Optional[int] = None
    gang_id: Optional[int] = None
    depth: int
    node_count: int
    edge_count: int
    relationship_types: List[str]
    source: str


class NetworkGraphOut(BaseModel):
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]
    metadata: NetworkMetadata


# ── Password recovery schemas ────────────────────────────────────────────────
class PasswordRecoveryRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=100)


class PasswordRecoveryVerify(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=100)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordReset(BaseModel):
    reset_token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=128)


Token.model_rebuild()
