from datetime import date
from typing import Dict, List, Literal, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.checkin import OrdinalOption

Language = Literal["en", "ta", "hi"]

class EnrollmentProcedure(BaseModel):
    procedure_code: str
    procedure_name: str
    observation_days: int
    ruleset_version: str

class BaselineParameter(BaseModel):
    code: str
    name: str
    type: Literal["numeric", "ordinal"]
    unit: Optional[str] = None
    value_min: Optional[float] = None
    value_max: Optional[float] = None
    decimals: int = 0
    options: List[OrdinalOption] = Field(default_factory=list)

class EnrollmentOptions(BaseModel):
    procedures: List[EnrollmentProcedure]
    languages: List[Language]
    baseline_parameters: List[BaselineParameter]
    today: date = Field(..., description="Today in the hospital's timezone; discharge cannot be later")

class EnrollmentRequest(BaseModel):
    patient_name: str = Field(..., min_length=1, max_length=200)
    mrn: str = Field(..., min_length=1, max_length=50)
    phone_e164: str = Field(..., pattern=r"^\+[1-9][0-9]{7,14}$")
    language_code: Language
    date_of_birth: Optional[date] = None
    procedure_code: str = Field(..., min_length=1, max_length=20)
    surgery_date: date
    discharge_date: date
    consent_version: str = Field(..., min_length=1, max_length=20)
    consent_confirmed: Literal[True] = Field(..., description="The patient's consent to monitoring was obtained")
    baseline: Dict[str, Union[float, str]] = Field(default_factory=dict)

    @field_validator("patient_name", "mrn", "consent_version")
    @classmethod
    def stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.discharge_date < self.surgery_date:
            raise ValueError("discharge_date cannot be before surgery_date")
        if self.date_of_birth and self.date_of_birth >= self.surgery_date:
            raise ValueError("date_of_birth must be before surgery_date")
        return self

class EnrollmentResponse(BaseModel):
    episode_id: UUID
    patient_id: UUID
    returning_patient: bool = Field(..., description="True when the MRN matched an existing patient")
    monitoring_ends_on: date
    post_op_day: int
    baseline_recorded: int
