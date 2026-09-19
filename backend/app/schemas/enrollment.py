import re
from datetime import date, time
from typing import Annotated, Dict, List, Literal, Optional, Union
from uuid import UUID
from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, field_validator, model_validator

from app.schemas.checkin import OrdinalOption

Language = Literal["en", "ta", "hi"]
Gender = Literal["male", "female", "other", "unknown"]  # FHIR administrative gender
Relationship = Literal["spouse", "son", "daughter", "sibling", "parent", "other_family", "friend", "caregiver"]
CheckInWindowCode = Literal["morning", "midday", "evening"]
PrivacyLaw = Literal["DPDP-2023", "HIPAA"]

_PHONE_SEPARATORS = re.compile(r"[\s\-().]")


def _normalise_phone(value):
    """Numbers are typed the way they are printed: '+91 98765 43210', '+91-98765-43210'."""
    return _PHONE_SEPARATORS.sub("", value) if isinstance(value, str) else value


def _blank_to_none(value):
    if isinstance(value, str):
        return value.strip() or None
    return value


Phone = Annotated[str, BeforeValidator(_normalise_phone), StringConstraints(pattern=r"^\+[1-9][0-9]{7,14}$")]
OptionalPhone = Annotated[Optional[Phone], BeforeValidator(_blank_to_none)]
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalText = Annotated[Optional[Annotated[str, StringConstraints(max_length=100)]], BeforeValidator(_blank_to_none)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


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

class CheckInWindow(BaseModel):
    code: CheckInWindowCode
    label: str
    start: time = Field(..., description="Hospital local time")
    end: time

class EnrollmentOptions(BaseModel):
    procedures: List[EnrollmentProcedure]
    languages: List[Language]
    baseline_parameters: List[BaselineParameter]
    checkin_windows: List[CheckInWindow]
    privacy_law: PrivacyLaw = Field(..., description="The law consent is recorded under at this hospital")
    today: date = Field(..., description="Today in the hospital's timezone; discharge cannot be later")

class AddressIn(BaseModel):
    """Home address, for an ambulance or a home visit (FHIR Patient.address)."""
    line: RequiredText
    city: OptionalText = None
    district: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    state: OptionalText = None
    postal_code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9 -]{3,10}$")]

class EmergencyContactIn(BaseModel):
    """Someone to call when the patient cannot answer (FHIR Patient.contact)."""
    name: RequiredText
    relationship: Relationship
    phone_e164: Phone

class EnrollmentRequest(BaseModel):
    patient_name: str = Field(..., min_length=1, max_length=200)
    mrn: str = Field(..., min_length=1, max_length=50)
    phone_e164: Phone
    language_code: Language
    date_of_birth: Optional[date] = None
    gender: Gender
    address: AddressIn
    alt_phone_e164: OptionalPhone = Field(None, description="SMS fallback if WhatsApp is unavailable")
    email: Annotated[Optional[Email], BeforeValidator(_blank_to_none)] = None
    emergency_contacts: List[EmergencyContactIn] = Field(..., min_length=1, max_length=3,
                                                         description="In the order to call them")
    procedure_code: str = Field(..., min_length=1, max_length=20)
    surgery_date: date
    discharge_date: date
    checkin_window: CheckInWindowCode
    consent_version: str = Field(..., min_length=1, max_length=20)
    consent_confirmed: Literal[True] = Field(..., description="The patient's consent to monitoring was obtained")
    data_processing_consent: Literal[True] = Field(
        ..., description="Consent to storing and processing health data in the cloud, under the hospital's privacy law")
    contact_sharing_consent: bool = Field(
        ..., description="Whether the care team may discuss the patient's recovery with the emergency contacts")
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

    @model_validator(mode="after")
    def contacts_reach_someone_else(self):
        # A contact on the patient's own number, or two on one number, adds no one to call.
        phones = [c.phone_e164 for c in self.emergency_contacts]
        if self.phone_e164 in phones:
            raise ValueError("an emergency contact needs a different number from the patient's WhatsApp number")
        if len(set(phones)) != len(phones):
            raise ValueError("each emergency contact needs a different phone number")
        if self.alt_phone_e164 == self.phone_e164:
            raise ValueError("the SMS number must differ from the WhatsApp number")
        return self

class EnrollmentResponse(BaseModel):
    episode_id: UUID
    patient_id: UUID
    returning_patient: bool = Field(..., description="True when the MRN matched an existing patient")
    monitoring_ends_on: date
    post_op_day: int
    baseline_recorded: int
