import uuid
from datetime import datetime, date
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
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models.base import Base

class Hospital(Base):
    __tablename__ = "hospital"
    __table_args__ = {"schema": "meta"}

    hospital_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hospital_name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Kolkata")
    ack_window_secs: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    privacy_law: Mapped[str] = mapped_column(Text, nullable=False, default="DPDP-2023")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    admins: Mapped[List["AdminUser"]] = relationship("AdminUser", back_populates="hospital")

class AdminUser(Base):
    __tablename__ = "admin_user"
    __table_args__ = (
        UniqueConstraint("hospital_id", "email", name="admin_user_hospital_email_unique"),
        {"schema": "meta"},
    )

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    # Null for an app admin, who belongs to no hospital.
    hospital_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("meta.hospital.hospital_id"), nullable=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="admins")

class SurgicalProcedure(Base):
    __tablename__ = "surgical_procedure"
    __table_args__ = {"schema": "meta"}

    procedure_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procedure_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    procedure_name: Mapped[str] = mapped_column(Text, nullable=False)
    procedure_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observation_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class HospitalProcedure(Base):
    __tablename__ = "hospital_procedure"
    __table_args__ = {"schema": "meta"}

    hospital_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.hospital.hospital_id"), primary_key=True)
    procedure_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.surgical_procedure.procedure_id"), primary_key=True)
    enabled_on: Mapped[date] = mapped_column(Date, server_default=text("current_date"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class Parameter(Base):
    __tablename__ = "parameter"
    __table_args__ = {"schema": "meta"}

    parameter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parameter_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parameter_name: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameter_type: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    value_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    decimal_places: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    concerning_when_true: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    loinc_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    options: Mapped[List["ParameterOption"]] = relationship("ParameterOption", back_populates="parameter")

class ParameterOption(Base):
    __tablename__ = "parameter_option"
    __table_args__ = {"schema": "meta"}

    parameter_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.parameter.parameter_id"), primary_key=True)
    option_code: Mapped[str] = mapped_column(Text, primary_key=True)
    option_label: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal_rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Relationships
    parameter: Mapped["Parameter"] = relationship("Parameter", back_populates="options")

class Ruleset(Base):
    __tablename__ = "ruleset"
    __table_args__ = {"schema": "meta"}

    ruleset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procedure_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.surgical_procedure.procedure_id"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    review_at: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    critical_at: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_points_per_parameter: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=6)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    approved_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Relationships
    procedure_parameters: Mapped[List["ProcedureParameter"]] = relationship("ProcedureParameter", back_populates="ruleset")

class ProcedureParameter(Base):
    __tablename__ = "procedure_parameter"
    __table_args__ = {"schema": "meta"}

    ruleset_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.ruleset.ruleset_id"), primary_key=True)
    parameter_id: Mapped[int] = mapped_column(Integer, ForeignKey("meta.parameter.parameter_id"), primary_key=True)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    display_section: Mapped[str] = mapped_column(Text, nullable=False, default="readings")
    collect_from_day: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    collect_to_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score_from_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score_to_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parameter_weight: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    scoring_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nurse_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    ruleset: Mapped["Ruleset"] = relationship("Ruleset", back_populates="procedure_parameters")
    parameter: Mapped["Parameter"] = relationship("Parameter")
