from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class EpisodeOption(BaseModel):
    """One selectable episode for the check-in simulator dropdown."""
    episode_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    procedure_code: str
    post_op_day: int
    monitoring_ends_on: date
    checked_in_today: bool

class OrdinalOption(BaseModel):
    code: str
    label: str
    rank: int

class FormParameter(BaseModel):
    """A question the approved ruleset says to collect on this post-op day."""
    parameter_id: int
    code: str
    name: str
    question_text: str
    type: str = Field(..., description="numeric, boolean or ordinal")
    section: str = Field(..., description="readings, checks or progress")
    unit: Optional[str] = None
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    decimals: int = 0
    is_mandatory: bool = False
    is_emergency: bool = Field(False, description="scoring_config.emergency — needs immediate contact, not triage")
    is_scored_today: bool = Field(True, description="False when collected but outside the scoring window")
    options: List[OrdinalOption] = Field(default_factory=list)

class FormSection(BaseModel):
    key: str
    parameters: List[FormParameter]

class EpisodeContext(BaseModel):
    episode_id: UUID
    patient_name: str
    first_name: str
    mrn: Optional[str] = None
    hospital_name: str
    procedure_code: str
    actual_post_op_day: int
    monitoring_ends_on: date

class CheckInForm(BaseModel):
    episode: EpisodeContext
    ruleset_id: int
    effective_day: int
    simulated: bool = Field(False, description="True when effective_day was overridden for demonstration")
    already_submitted_today: bool
    sections: List[FormSection]

class CheckInValueIn(BaseModel):
    parameter_id: int
    value_num: Optional[float] = None
    value_bool: Optional[bool] = None
    value_code: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_value(self):
        provided = sum(
            v is not None for v in (self.value_num, self.value_bool, self.value_code)
        )
        if provided != 1:
            raise ValueError(
                "exactly one of value_num, value_bool or value_code must be set "
                "(unanswered parameters are omitted entirely, not sent as null)"
            )
        return self

class CheckInSubmit(BaseModel):
    episode_id: UUID
    day_after_discharge: int = Field(..., ge=0, le=365)
    idempotency_key: str = Field(..., min_length=8, max_length=200)
    simulated: bool = False
    values: List[CheckInValueIn] = Field(default_factory=list)

class CheckInReceipt(BaseModel):
    check_in_id: UUID
    episode_id: UUID
    day_after_discharge: int
    source: str
    submitted_at: datetime
    values_recorded: int
    superseded_count: int = Field(0, description="Earlier live check-ins for this day that this submission replaced")
    duplicate: bool = Field(False, description="True when the idempotency key replayed an earlier submission")
