from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, Enum, JSON,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
import enum
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    investigating_officer = "investigating_officer"
    record_clerk = "record_clerk"


class CaseStatus(str, enum.Enum):
    open = "open"
    under_investigation = "under_investigation"
    closed = "closed"
    archived = "archived"


class PredictionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    overridden = "overridden"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.record_clerk)
    badge_number = Column(String(20), nullable=True)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    # Account security state
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")
    failed_login_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)
    # Incremented whenever all existing sessions must be invalidated
    # (password change/reset, deactivation, role change).
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    cases_assigned = relationship("Case", back_populates="assigned_officer", foreign_keys="Case.assigned_officer_id")
    audit_logs = relationship("AuditLog", back_populates="user")
    ai_reviews = relationship("AIPrediction", back_populates="reviewed_by_officer")


class RevokedToken(Base):
    """Denylist of individually revoked access tokens (e.g. on logout)."""
    __tablename__ = "revoked_tokens"

    jti = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PasswordRecovery(Base):
    __tablename__ = "password_recovery"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    request_ip = Column(String(45), nullable=True, index=True)
    otp_hash = Column(String(64), nullable=False)
    otp_expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    reset_token_hash = Column(String(64), nullable=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    reset_consumed_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class Gang(Base):
    __tablename__ = "gangs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    alias = Column(String(200), nullable=True)
    territory = Column(String(200), nullable=True)
    threat_level = Column(String(20), default="medium")  # low, medium, high, critical
    active_since = Column(DateTime(timezone=True), nullable=True)
    known_activities = Column(Text, nullable=True)
    member_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("Criminal", back_populates="gang")


class Criminal(Base):
    __tablename__ = "criminals"
    __table_args__ = (Index("ix_criminals_gang", "gang_id"), Index("ix_criminals_wanted_risk", "is_wanted", "risk_score"),)

    id = Column(Integer, primary_key=True, index=True)
    crn = Column(String(20), unique=True, index=True, nullable=False)  # Criminal Record Number
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    alias = Column(String(200), nullable=True)
    date_of_birth = Column(DateTime(timezone=True), nullable=True)
    gender = Column(String(10), nullable=True)
    nationality = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    occupation = Column(String(100), nullable=True)
    photo_url = Column(String(500), nullable=True)
    # Uploaded photo in the content-addressed file store (app/utils/file_store.py).
    photo_sha256 = Column(String(64), nullable=True)
    photo_content_type = Column(String(50), nullable=True)
    fingerprint_id = Column(String(100), nullable=True)

    # Crime profile
    crime_type = Column(String(100), nullable=True)
    crime_category = Column(String(50), nullable=True)
    prior_convictions = Column(Integer, default=0)
    modus_operandi = Column(Text, nullable=True)
    known_associates = Column(Text, nullable=True)

    # Gang affiliation
    gang_id = Column(Integer, ForeignKey("gangs.id"), nullable=True)
    gang_rank = Column(String(50), nullable=True)

    # Status
    is_wanted = Column(Boolean, default=False)
    is_incarcerated = Column(Boolean, default=False)
    threat_level = Column(String(20), default="low")
    risk_score = Column(Float, default=0.0)

    # Metadata
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    gang = relationship("Gang", back_populates="members")
    cases = relationship("CaseCriminal", back_populates="criminal", cascade="all, delete-orphan")
    ai_predictions = relationship("AIPrediction", back_populates="criminal")
    history_records = relationship("CriminalHistory", back_populates="criminal", cascade="all, delete-orphan")


class CriminalHistory(Base):
    __tablename__ = "criminal_history"

    id = Column(Integer, primary_key=True, index=True)
    criminal_id = Column(Integer, ForeignKey("criminals.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # arrest, conviction, release, etc.
    description = Column(Text, nullable=True)
    date = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(200), nullable=True)
    case_reference = Column(String(50), nullable=True)
    recorded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    criminal = relationship("Criminal", back_populates="history_records")


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (Index("uq_cases_fir_number", "fir_number", unique=True), Index("ix_cases_assigned_status", "assigned_officer_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    case_number = Column(String(30), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    crime_type = Column(String(100), nullable=True)
    crime_category = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    incident_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(CaseStatus), default=CaseStatus.open)
    priority = Column(String(20), default="normal")  # low, normal, high, critical

    # Incident facts recorded by the investigating officer. These are the
    # observed inputs for the AI crime-type model (see app/ml/FEATURE_CONTRACT.md).
    # NULL means "not recorded" and is kept distinct from an explicit "no"
    # (the prediction reports it as a defaulted input).
    weapons_involved = Column(Boolean, nullable=True)
    drug_involvement = Column(Boolean, nullable=True)
    financial_motivation = Column(Boolean, nullable=True)
    tech_involvement = Column(Boolean, nullable=True)

    # FIR
    fir_number = Column(String(30), nullable=True)
    fir_date = Column(DateTime(timezone=True), nullable=True)
    fir_filed_by = Column(String(100), nullable=True)
    fir_station = Column(String(100), nullable=True)
    complainant_name = Column(String(100), nullable=True)
    complainant_contact = Column(String(20), nullable=True)

    # Assignment
    assigned_officer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    assigned_officer = relationship("User", back_populates="cases_assigned", foreign_keys=[assigned_officer_id])
    criminals = relationship("CaseCriminal", back_populates="case", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")
    victims = relationship("Victim", back_populates="case", cascade="all, delete-orphan")
    ai_predictions = relationship("AIPrediction", back_populates="case", cascade="all, delete-orphan")


class CaseCriminal(Base):
    __tablename__ = "case_criminals"
    __table_args__ = (UniqueConstraint("case_id", "criminal_id", name="uq_case_criminal"),)

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    criminal_id = Column(Integer, ForeignKey("criminals.id"), nullable=False, index=True)
    role = Column(String(50), nullable=True)  # suspect, accused, convicted
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="criminals")
    criminal = relationship("Criminal", back_populates="cases")


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("case_id", "evidence_number", name="uq_case_evidence_number"),)

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    evidence_number = Column(String(30), nullable=False)
    type = Column(String(50), nullable=True)  # physical, digital, forensic, witness
    description = Column(Text, nullable=True)
    location_found = Column(String(200), nullable=True)
    collected_by = Column(String(100), nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=True)
    chain_of_custody = Column(Text, nullable=True)
    status = Column(String(30), default="collected")
    file_url = Column(String(500), nullable=True)
    # SHA-256 of the referenced evidence file, recorded at collection time so
    # later copies can be verified against the original.
    file_sha256 = Column(String(64), nullable=True)
    # Set when the file itself was uploaded into the file store (not just referenced).
    file_content_type = Column(String(50), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="evidence")


class Victim(Base):
    __tablename__ = "victims"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    injury_description = Column(Text, nullable=True)
    status = Column(String(30), default="alive")  # alive, deceased, hospitalized
    statement = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="victims")


class AIPrediction(Base):
    __tablename__ = "ai_predictions"
    __table_args__ = (Index("ix_ai_predictions_criminal_created", "criminal_id", "created_at"), Index("ix_ai_predictions_case_created", "case_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    criminal_id = Column(Integer, ForeignKey("criminals.id"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)

    # Prediction results
    predicted_crime_type = Column(String(100), nullable=True)
    crime_type_confidence = Column(Float, default=0.0)
    gang_affiliation_probability = Column(Float, default=0.0)
    predicted_gang_id = Column(Integer, ForeignKey("gangs.id"), nullable=True)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(20), default="low")
    confidence_overall = Column(Float, default=0.0)

    # Similar records
    similar_criminals = Column(JSON, nullable=True)  # list of criminal ids + scores
    similar_cases = Column(JSON, nullable=True)

    # Feature inputs used
    input_features = Column(JSON, nullable=True)

    # Officer review
    review_status = Column(Enum(PredictionStatus), default=PredictionStatus.pending)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    officer_remarks = Column(Text, nullable=True)
    override_crime_type = Column(String(100), nullable=True)

    # Model version
    model_version = Column(String(20), default="v1.0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    criminal = relationship("Criminal", back_populates="ai_predictions")
    case = relationship("Case", back_populates="ai_predictions")
    reviewed_by_officer = relationship("User", back_populates="ai_reviews")
    reviews = relationship(
        "AIPredictionReview", back_populates="prediction",
        cascade="all, delete-orphan", order_by="AIPredictionReview.id",
    )


class AIPredictionReview(Base):
    """Append-only history of human decisions on an AI prediction.

    Every confirm/reject/override (and every later correction) is kept, with
    the reviewer and their stated reason, so decisions can be contested and
    audited. The latest row mirrors the summary fields on ``AIPrediction``.
    """
    __tablename__ = "ai_prediction_reviews"
    __table_args__ = (Index("ix_ai_prediction_reviews_prediction", "prediction_id", "id"),)

    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey("ai_predictions.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_username = Column(String(50), nullable=True)
    previous_status = Column(String(20), nullable=True)
    decision = Column(String(20), nullable=False)
    remarks = Column(Text, nullable=False)
    override_crime_type = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    prediction = relationship("AIPrediction", back_populates="reviews")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_target_user_read", "target_user_id", "is_read"), Index("ix_notifications_role_read", "target_role", "is_read"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(30), default="info")  # info, warning, alert, success
    is_read = Column(Boolean, default=False)
    target_role = Column(String(30), nullable=True)  # null = all, or specific role
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    related_criminal_id = Column(Integer, ForeignKey("criminals.id"), nullable=True)
    related_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    # Prevents the same alert being raised repeatedly for one underlying event.
    dedup_key = Column(String(120), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotificationRead(Base):
    """Per-user read receipt. Role/broadcast notifications are shared rows, so
    read state must be tracked per recipient rather than on the notification."""
    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uq_notification_read"),)

    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_action_created", "action", "created_at"), Index("ix_audit_logs_resource", "resource_type", "resource_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(50), nullable=True)
    role = Column(String(30), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="success")
    reason = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    # Correlates the audit event with application logs for the same request.
    request_id = Column(String(64), nullable=True, index=True)
    # HMAC-SHA256 over the canonical entry content (keyed with SECRET_KEY) so
    # any later modification of a stored row is detectable.
    entry_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())

    user = relationship("User", back_populates="audit_logs")


class MLModel(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(20), nullable=False)
    model_type = Column(String(50), nullable=False)  # crime_classifier, gang_predictor
    accuracy = Column(Float, default=0.0)
    precision_score = Column(Float, default=0.0)
    recall_score = Column(Float, default=0.0)
    f1_score = Column(Float, default=0.0)
    training_samples = Column(Integer, default=0)
    feature_importances = Column(JSON, nullable=True)
    evaluation_metadata = Column(JSON, nullable=True)
    dataset_version = Column(String(50), nullable=True)
    evaluation_method = Column(String(120), nullable=True)
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    activated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True, index=True)
    value = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
