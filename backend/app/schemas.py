from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


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


# ── Auth Schemas ─────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    user: "UserOut"


class TokenData(BaseModel):
    username: Optional[str] = None


# ── User Schemas ─────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username: str
    email: str
    full_name: str
    role: UserRole
    badge_number: Optional[str] = None
    department: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    badge_number: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Gang Schemas ─────────────────────────────────────────────────────────────
class GangBase(BaseModel):
    name: str
    alias: Optional[str] = None
    territory: Optional[str] = None
    threat_level: Optional[str] = "medium"
    known_activities: Optional[str] = None
    member_count: Optional[int] = 0
    is_active: Optional[bool] = True


class GangCreate(GangBase):
    pass


class GangUpdate(GangBase):
    name: Optional[str] = None


class GangOut(GangBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Criminal Schemas ─────────────────────────────────────────────────────────
class CriminalBase(BaseModel):
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


class CriminalCreate(CriminalBase):
    pass


class CriminalUpdate(CriminalBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class CriminalHistoryItem(BaseModel):
    id: int
    event_type: str
    description: Optional[str]
    date: Optional[datetime]
    location: Optional[str]
    case_reference: Optional[str]
    recorded_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CriminalOut(CriminalBase):
    id: int
    crn: str
    risk_score: float
    created_at: datetime
    updated_at: Optional[datetime]
    gang: Optional[GangOut] = None

    class Config:
        from_attributes = True


class DuplicateCheckResult(BaseModel):
    has_duplicates: bool
    duplicates: List[CriminalOut]
    match_score: float


# ── Case / FIR Schemas ───────────────────────────────────────────────────────
class CaseBase(BaseModel):
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


class CaseCreate(CaseBase):
    criminal_ids: Optional[List[int]] = []


class CaseUpdate(CaseBase):
    title: Optional[str] = None
    status: Optional[CaseStatus] = None
    criminal_ids: Optional[List[int]] = None


class CaseCriminalOut(BaseModel):
    id: int
    criminal_id: int
    role: Optional[str]
    criminal: CriminalOut

    class Config:
        from_attributes = True


class EvidenceOut(BaseModel):
    id: int
    evidence_number: str
    type: Optional[str]
    description: Optional[str]
    location_found: Optional[str]
    collected_by: Optional[str]
    collected_at: Optional[datetime]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class CaseOut(CaseBase):
    id: int
    case_number: str
    status: CaseStatus
    created_at: datetime
    updated_at: Optional[datetime]
    assigned_officer: Optional[UserOut] = None
    criminals: List[CaseCriminalOut] = []
    evidence: List[EvidenceOut] = []
    victims: List[VictimOut] = []

    class Config:
        from_attributes = True


# ── Evidence & Victim Schemas ────────────────────────────────────────────────
class EvidenceCreate(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    location_found: Optional[str] = None
    collected_by: Optional[str] = None
    collected_at: Optional[datetime] = None
    chain_of_custody: Optional[str] = None
    status: Optional[str] = "collected"


class VictimCreate(BaseModel):
    first_name: str
    last_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    injury_description: Optional[str] = None
    status: Optional[str] = "alive"
    statement: Optional[str] = None


# ── AI Prediction Schemas ────────────────────────────────────────────────────
class PredictionRequest(BaseModel):
    criminal_id: Optional[int] = None
    case_id: Optional[int] = None


class SimilarRecord(BaseModel):
    id: int
    name: str
    score: float
    crime_type: Optional[str]


class AIPredictionOut(BaseModel):
    id: int
    criminal_id: Optional[int]
    case_id: Optional[int]
    predicted_crime_type: Optional[str]
    crime_type_confidence: float
    gang_affiliation_probability: float
    predicted_gang_id: Optional[int]
    risk_score: float
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

    class Config:
        from_attributes = True


class PredictionReview(BaseModel):
    status: PredictionStatus
    remarks: Optional[str] = None
    override_crime_type: Optional[str] = None


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

    class Config:
        from_attributes = True


# ── Audit Log Schemas ────────────────────────────────────────────────────────
class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    details: Optional[Any]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


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
    trained_at: datetime
    is_active: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


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
    prediction_accuracy: float


# ── System Setting Schemas ───────────────────────────────────────────────────
class SystemSettingBase(BaseModel):
    value: str
    description: Optional[str] = None


class SystemSettingUpdate(SystemSettingBase):
    pass


class SystemSettingOut(SystemSettingBase):
    key: str
    updated_at: Optional[datetime]
    updated_by_id: Optional[int]

    class Config:
        from_attributes = True
