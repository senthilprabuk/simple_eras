from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.episode import OperativeSide

#: Whether today's check-in is in. Derived on the server because "today" is the
#: hospital's own date, and a browser in another timezone would disagree about
#: which post-operative day it currently is.
#:   done      today's post-operative day has a check-in
#:   pending   it is due and has not arrived
#:   none_yet  this patient has never checked in at all
#:   not_due   no check-in is expected today: the episode is closed, or today
#:             falls outside its monitoring window
CheckInToday = Literal["done", "pending", "none_yet", "not_due"]

class PatientListItem(BaseModel):
    episode_id: UUID
    patient_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    phone_e164: Optional[str] = Field(
        None, description="The patient's own number, so a poor adherence row can be acted on from the list")
    language_code: str
    procedure_code: str
    operative_side: Optional[OperativeSide] = Field(
        None, description="Which knee was replaced; null for episodes enrolled before it was captured")
    discharge_date: date
    monitoring_ends_on: date
    status: str
    post_op_day: int
    enrolled_at: datetime
    enrolled_by_name: Optional[str] = None
    last_check_in_day: Optional[int] = None
    last_check_in_at: Optional[datetime] = None
    check_in_today: CheckInToday = Field(
        ..., description="Whether today's check-in is in, so the list does not have to be read as dates")
    check_in_days: int = Field(..., description="Days with at least one check-in")
    expected_check_in_days: int = Field(..., description="Days from discharge to today, within the monitoring period")
    adherence_pct: Optional[float] = None
    open_alerts: int
    top_open_tier: Optional[str] = None

class PatientListResponse(BaseModel):
    items: List[PatientListItem]
    total: int
    limit: int
    offset: int

class TrendPoint(BaseModel):
    day: int
    date: date
    value: Optional[float] = Field(None, description="Null when there was no check-in or no answer that day")
    threshold: Optional[float] = Field(None, description="Where the ruleset starts scoring; null outside its scoring window")
    collected: bool = Field(..., description="Whether the ruleset asks this question on this day")

class Trend(BaseModel):
    code: str
    name: str
    unit: Optional[str] = None
    decimals: int
    baseline: Optional[float] = None
    threshold_direction: Optional[Literal["above", "below"]] = None
    scoring_rule: str
    points: List[TrendPoint]

class ObservationCell(BaseModel):
    value: Optional[bool] = Field(None, description="Null when not answered")
    asked: bool = Field(..., description="Whether the ruleset asks this question on this day")

class ObservationColumn(BaseModel):
    code: str
    name: str
    question_text: Optional[str] = None
    is_emergency: bool

class ObservationRow(BaseModel):
    day: int
    date: date
    checked_in: bool
    source: Optional[str] = None
    values: Dict[str, ObservationCell]

class PatientTimeline(BaseModel):
    episode_id: UUID
    post_op_day: int
    trends: List[Trend]
    observation_columns: List[ObservationColumn]
    observations: List[ObservationRow] = Field(..., description="One row per day, oldest first")
