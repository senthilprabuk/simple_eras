import uuid
from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Integer,
    SmallInteger,
    Text,
    Boolean,
    Numeric,
    DateTime,
    Date,
    Time,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models.base import Base

class Patient(Base):
    __tablename__ = "patient"
    __table_args__ = {"schema": "txn"}

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    hospital_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.hospital.hospital_id"), nullable=False)
    mrn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patient_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone_e164: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    address_line: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_postal_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alt_phone_e164: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    episodes: Mapped[List["PatientEpisode"]] = relationship("PatientEpisode", back_populates="patient")
    contacts: Mapped[List["PatientContact"]] = relationship("PatientContact", order_by="PatientContact.priority")

class PatientContact(Base):
    __tablename__ = "patient_contact"
    __table_args__ = {"schema": "txn"}

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient.patient_id"), primary_key=True)
    priority: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(Text, nullable=False)
    phone_e164: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class PatientEpisode(Base):
    __tablename__ = "patient_episode"
    __table_args__ = {"schema": "txn"}

    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient.patient_id"), nullable=False)
    hospital_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.hospital.hospital_id"), nullable=False)
    procedure_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.surgical_procedure.procedure_id"), nullable=False)
    ruleset_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.ruleset.ruleset_id"), nullable=False)
    surgery_date: Mapped[date] = mapped_column(Date, nullable=False)
    discharge_date: Mapped[date] = mapped_column(Date, nullable=False)
    monitoring_ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enrolled_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("meta.admin_user.admin_user_id"), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    checkin_window_start: Mapped[time] = mapped_column(Time, nullable=False, server_default=text("'08:00'"))
    checkin_window_end: Mapped[time] = mapped_column(Time, nullable=False, server_default=text("'10:00'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="episodes")
    check_ins: Mapped[List["PatientCheckIn"]] = relationship("PatientCheckIn", back_populates="episode")
    evaluations: Mapped[List["CheckInEvaluation"]] = relationship("CheckInEvaluation", back_populates="episode")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="episode")

class EpisodeBaseline(Base):
    __tablename__ = "episode_baseline"
    __table_args__ = {"schema": "txn"}

    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_episode.episode_id"), primary_key=True)
    parameter_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.parameter.parameter_id"), primary_key=True)
    value_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    value_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class EpisodeConsent(Base):
    __tablename__ = "episode_consent"
    __table_args__ = {"schema": "txn"}

    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_episode.episode_id"), primary_key=True)
    consent_code: Mapped[str] = mapped_column(Text, primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    privacy_law: Mapped[str] = mapped_column(Text, nullable=False)
    form_version: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("meta.admin_user.admin_user_id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class PatientCheckIn(Base):
    __tablename__ = "patient_check_in"
    __table_args__ = {"schema": "txn"}

    check_in_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_episode.episode_id"), nullable=False)
    day_after_discharge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="patient")
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    episode: Mapped["PatientEpisode"] = relationship("PatientEpisode", back_populates="check_ins")
    values: Mapped[List["PatientCheckInValue"]] = relationship("PatientCheckInValue", back_populates="check_in")

class PatientCheckInValue(Base):
    __tablename__ = "patient_check_in_value"
    __table_args__ = {"schema": "txn"}

    check_in_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_check_in.check_in_id"), primary_key=True)
    parameter_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.parameter.parameter_id"), primary_key=True)
    value_num: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    value_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    check_in: Mapped["PatientCheckIn"] = relationship("PatientCheckIn", back_populates="values")

class CheckInEvaluation(Base):
    __tablename__ = "check_in_evaluation"
    __table_args__ = {"schema": "txn"}

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    check_in_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_check_in.check_in_id"), nullable=True)
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_episode.episode_id"), nullable=False)
    ruleset_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.ruleset.ruleset_id"), nullable=False)
    day_after_discharge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    total_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasons: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    reason_key: Mapped[str] = mapped_column(Text, nullable=False)
    coverage: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    episode: Mapped["PatientEpisode"] = relationship("PatientEpisode", back_populates="evaluations")
    alert: Mapped[Optional["Alert"]] = relationship("Alert", back_populates="evaluation", uselist=False)

class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = {"schema": "txn"}

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.patient_episode.episode_id"), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.check_in_evaluation.evaluation_id"), nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    reason_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("meta.admin_user.admin_user_id"), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("meta.admin_user.admin_user_id"), nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    episode: Mapped["PatientEpisode"] = relationship("PatientEpisode", back_populates="alerts")
    evaluation: Mapped["CheckInEvaluation"] = relationship("CheckInEvaluation", back_populates="alert")
    notifications: Mapped[List["AlertNotification"]] = relationship("AlertNotification", back_populates="alert")

class AlertNotification(Base):
    __tablename__ = "alert_notification"
    __table_args__ = {"schema": "txn"}

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("txn.alert.alert_id"), nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    alert: Mapped["Alert"] = relationship("Alert", back_populates="notifications")
