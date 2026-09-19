from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class OfferedProcedure(BaseModel):
    procedure_code: str
    procedure_name: str
    observation_days: int
    enabled_on: date
    is_active: bool

class HospitalStats(BaseModel):
    active_patients: int
    completed_patients: int
    active_clinicians: int
    unresolved_alerts: int
    check_ins_last_7_days: int

class HospitalProfile(BaseModel):
    hospital_id: int
    hospital_code: str
    hospital_name: str
    city: Optional[str] = None
    timezone: str
    ack_window_secs: int
    is_active: bool
    procedures: List[OfferedProcedure]
    stats: HospitalStats

class HospitalUpdate(BaseModel):
    """Only the fields sent are changed."""
    hospital_name: Optional[str] = Field(None, min_length=1, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)
    ack_window_secs: Optional[int] = Field(None, ge=60, le=7200)

    @field_validator("hospital_name")
    @classmethod
    def name_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value else value
