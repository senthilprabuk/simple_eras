import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.enrollment import PrivacyLaw
from app.services.scoring_config import Direction

RulesetStatus = Literal["draft", "approved", "retired"]


def _stripped(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class ProcedureOption(BaseModel):
    procedure_code: str
    procedure_name: str
    approved_version: Optional[str] = None

class PlatformOptions(BaseModel):
    procedures: List[ProcedureOption]
    privacy_laws: List[PrivacyLaw]
    timezones: List[str]

# ------------------------------------------------------------------ hospitals

class HospitalAccount(BaseModel):
    admin_user_id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

class PlatformHospital(BaseModel):
    hospital_id: int
    hospital_code: str
    hospital_name: str
    city: Optional[str] = None
    timezone: str
    ack_window_secs: int
    privacy_law: PrivacyLaw
    is_active: bool
    procedure_codes: List[str]
    account_count: int = Field(..., description="Active clinician accounts")
    active_patients: int
    created_at: datetime

class PlatformHospitalDetail(PlatformHospital):
    accounts: List[HospitalAccount]

class HospitalFields(BaseModel):
    hospital_name: str = Field(..., min_length=1, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    timezone: str = Field(..., min_length=1, max_length=64)
    ack_window_secs: int = Field(..., ge=60, le=7200, description="How long an alert may wait for acknowledgement before it escalates, in seconds")
    privacy_law: PrivacyLaw
    is_active: bool = True
    procedure_codes: List[str] = Field(default_factory=list, description="Procedures this hospital enrolls patients for")

    @field_validator("hospital_name", "timezone")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return _stripped(value)

    @field_validator("city")
    @classmethod
    def blank_city_is_none(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None

class HospitalCreate(HospitalFields):
    hospital_code: str = Field(..., description="Short, permanent key such as CBE-02")

    @field_validator("hospital_code")
    @classmethod
    def code_shape(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,19}", value):
            raise ValueError("use 2-20 letters, digits or dashes, e.g. CBE-02")
        return value

class HospitalUpdate(HospitalFields):
    """Everything but the code, which other systems may key on."""

# ------------------------------------------------------------------- rulesets

class PlatformRulesetVersion(BaseModel):
    ruleset_id: int
    version: str
    status: RulesetStatus
    review_at: int
    critical_at: int
    max_points_per_parameter: int
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    parameter_count: int
    active_episodes: int = Field(..., description="Patients being monitored under this version now")
    total_episodes: int

class PlatformProcedureRulesets(BaseModel):
    procedure_code: str
    procedure_name: str
    observation_days: int
    hospitals_offering: int
    versions: List[PlatformRulesetVersion]

class RulesetBinding(BaseModel):
    parameter_code: str
    parameter_name: str
    parameter_type: str
    unit: Optional[str] = None
    display_section: str
    display_order: int
    collect_from_day: int
    collect_to_day: int
    score_from_day: int
    score_to_day: int
    weight: int
    is_mandatory: bool
    question_text: Optional[str] = None
    nurse_script: Optional[str] = None
    scoring_config: Dict[str, Any]
    scoring_summary: str
    direction: Optional[Direction] = Field(None, description="Which way a numeric measure goes wrong; null for the other kinds")

class AvailableParameter(BaseModel):
    parameter_code: str
    parameter_name: str
    parameter_type: str
    unit: Optional[str] = None
    option_codes: List[str] = Field(default_factory=list)

class PlatformRulesetDetail(PlatformRulesetVersion):
    procedure_code: str
    procedure_name: str
    observation_days: int
    composite_config: Dict[str, Any] = Field(
        default_factory=dict, description="Signals that read every measure at once rather than belonging to one"
    )
    composite_summary: List[str] = Field(default_factory=list)
    bindings: List[RulesetBinding]
    available_parameters: List[AvailableParameter] = Field(..., description="Measures not yet in this version")

class DraftCreate(BaseModel):
    version: str = Field(..., description="The new version's name, e.g. 1.1.0")
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("version")
    @classmethod
    def version_shape(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.\-]{0,19}", value):
            raise ValueError("use up to 20 letters, digits, dots or dashes, e.g. 1.1.0")
        return value

class RulesetUpdate(BaseModel):
    review_at: Optional[int] = Field(None, ge=1, le=100)
    critical_at: Optional[int] = Field(None, ge=2, le=100)
    max_points_per_parameter: Optional[int] = Field(None, ge=1, le=30)
    notes: Optional[str] = Field(None, max_length=500)
    composite_config: Optional[Dict[str, Any]] = Field(
        None, description="Cross-measure signals; {} clears them"
    )

class BindingInput(BaseModel):
    display_section: Literal["readings", "checks", "progress"]
    display_order: int = Field(..., ge=1, le=99)
    collect_from_day: int = Field(..., ge=0, le=365)
    collect_to_day: int = Field(..., ge=0, le=365)
    score_from_day: int = Field(..., ge=0, le=365)
    score_to_day: int = Field(..., ge=0, le=365)
    weight: int = Field(..., ge=0, le=10)
    is_mandatory: bool = False
    question_text: str = Field(..., min_length=1, max_length=300, description="What the patient is asked")
    nurse_script: Optional[str] = Field(None, max_length=500)
    scoring_config: Dict[str, Any]

    @field_validator("question_text")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        return _stripped(value)

    @model_validator(mode="after")
    def windows_make_sense(self):
        if self.collect_to_day < self.collect_from_day:
            raise ValueError("the question must stop being asked after it starts")
        if self.score_to_day < self.score_from_day:
            raise ValueError("scoring must stop after it starts")
        if self.score_from_day < self.collect_from_day or self.score_to_day > self.collect_to_day:
            raise ValueError("an answer can only be scored on days it is asked")
        return self

class ApprovalRequest(BaseModel):
    approved_by: str = Field(..., min_length=1, max_length=200, description="The clinician who signed off this version")

    @field_validator("approved_by")
    @classmethod
    def approver_not_blank(cls, value: str) -> str:
        return _stripped(value)
