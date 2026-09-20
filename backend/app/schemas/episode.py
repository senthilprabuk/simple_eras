from datetime import date, datetime, time
from typing import List, Literal, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field

# bool first: in smart-mode unions an exact bool must not be read as a number.
ReadingValue = Union[bool, float, str]

# Mirrors episode_operative_side_known on txn.patient_episode. Defined here
# rather than in each schema that reports it, so the three screens showing a
# patient's operative knee cannot drift apart on what the values are.
OperativeSide = Literal["left", "right", "bilateral"]

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

class EmergencyContact(BaseModel):
    name: str
    relationship: str
    phone_e164: str

class Address(BaseModel):
    line: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None

class ConsentDecision(BaseModel):
    code: str = Field(..., description="remote_monitoring, data_processing or contact_sharing")
    granted: bool
    privacy_law: str
    recorded_at: datetime

class BodyMeasurements(BaseModel):
    """Recorded at enrollment. BMI is worked out from height and weight, never typed in."""
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None

class EpisodeSummary(BaseModel):
    """What a clinician needs beside an alert: who the patient is and their latest readings."""
    episode_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    phone_e164: str
    alt_phone_e164: Optional[str] = None
    email: Optional[str] = None
    gender: str
    date_of_birth: Optional[date] = None
    age_years: Optional[int] = None
    address: Optional[Address] = Field(None, description="Null when no address was recorded")
    emergency_contacts: List[EmergencyContact] = Field(default_factory=list, description="In the order to call them")
    hospital_name: str
    procedure_code: str
    procedure_name: str
    discharge_date: date
    post_op_day: int
    status: str
    ruleset_version: str
    checkin_window_start: time
    checkin_window_end: time
    consents: List[ConsentDecision] = Field(default_factory=list)
    body: BodyMeasurements
    latest_check_in: Optional[LatestCheckIn] = None
    readings: List[ParameterReading]
