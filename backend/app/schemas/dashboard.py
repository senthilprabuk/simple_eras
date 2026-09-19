from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Reason(BaseModel):
    """
    One clinical reason behind an alert. Scores and weights stored alongside it
    in the evaluation are dropped here: the clinical spec keeps numeric scores
    out of the nurse-facing queue.
    """
    model_config = ConfigDict(extra="ignore")

    name: str
    detail: Optional[str] = None

class QueueRow(BaseModel):
    """Single patient alert item in the risk-sorted triage queue."""
    alert_id: UUID
    patient_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    episode_id: UUID
    hospital_id: int
    hospital_name: str
    procedure_code: str
    day_after_discharge: int
    tier: str = Field(..., description="Severity tier: emergency, critical, review, missed")
    reasons: List[Reason]
    raised_at: datetime
    age_secs: int
    acknowledged: bool
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_name: Optional[str] = None
    ack_window_secs: int = Field(..., description="This hospital's acknowledgement SLA")

    @field_validator("reasons", mode="before")
    @classmethod
    def plain_strings_become_reasons(cls, value):
        return [{"name": r, "detail": r} if isinstance(r, str) else r for r in value]

class QueueResponse(BaseModel):
    """A page of the triage queue for the clinic dashboard."""
    items: List[QueueRow]
    total: int = Field(..., description="Unresolved alerts across all pages")
    limit: int
    offset: int

class KpiResponse(BaseModel):
    """Key Performance Indicators for the dashboard header cards."""
    active_patients: int = Field(..., description="Episodes currently under monitoring")
    patients_with_open_alerts: int = Field(..., description="Active episodes with at least one unresolved alert")
    unresolved_alerts: int = Field(..., description="Alerts not yet resolved (open or acknowledged)")
    unacknowledged_alerts: int = Field(..., description="Alerts nobody has acknowledged yet")
    ack_compliance_pct: Optional[float] = Field(
        ...,
        description=(
            "Share of alerts acknowledged within the hospital's window, among alerts raised in the "
            "rolling window that have a verdict: acknowledged, or past their deadline unacknowledged. "
            "Null when none has a verdict yet."
        ),
    )
    ack_decided_alerts: int = Field(..., description="Alerts counted in ack_compliance_pct")
    ack_window_secs: int = Field(..., description="This hospital's acknowledgement SLA")
    missed_checkins_today: int = Field(..., description="Missed check-ins evaluated today, in the hospital's timezone")
    window_days: int = Field(..., description="Rolling window in days for ack_compliance_pct")
