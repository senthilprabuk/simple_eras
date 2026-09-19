from datetime import date, datetime
from typing import List, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field

# bool first: in smart-mode unions an exact bool must not be read as a number.
ReadingValue = Union[bool, float, str]

class ParameterReading(BaseModel):
    """A parameter's discharge baseline beside the latest submitted value."""
    code: str
    name: str
    type: str = Field(..., description="numeric, boolean or ordinal")
    unit: Optional[str] = None
    decimals: int = 0
    concerning_when_true: Optional[bool] = None
    baseline: Optional[ReadingValue] = Field(None, description="Ordinals are returned as their label")
    current: Optional[ReadingValue] = Field(None, description="Null when not answered in the latest check-in")

class LatestCheckIn(BaseModel):
    check_in_id: UUID
    day_after_discharge: int
    submitted_at: datetime
    source: str
    photo_submitted: bool

class EpisodeSummary(BaseModel):
    """What a clinician needs beside an alert: who the patient is and their latest readings."""
    episode_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    phone_e164: str
    hospital_name: str
    procedure_code: str
    procedure_name: str
    discharge_date: date
    post_op_day: int
    status: str
    ruleset_version: str
    latest_check_in: Optional[LatestCheckIn] = None
    readings: List[ParameterReading]
