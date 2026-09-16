from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field

class QueueRow(BaseModel):
    """
    Single patient alert item in the risk-sorted triage queue.
    NOTE: Explicitly excludes numeric evaluation scores per clinical spec.
    """
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
    reasons: List[Any] = Field(default_factory=list, description="Array of clinical flag reason strings or objects")
    raised_at: datetime
    age_secs: int
    acknowledged: bool
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_name: Optional[str] = None

class QueueResponse(BaseModel):
    """List of triage queue items for the clinic dashboard."""
    items: List[QueueRow]
    total: int

class KpiResponse(BaseModel):
    """Key Performance Indicators for Page 1 dashboard header cards."""
    active_patients: int = Field(..., description="Active enrolled patients in monitoring program")
    open_alerts: int = Field(..., description="Active open and unacknowledged alerts requiring attention")
    ack_rate_15min: float = Field(..., description="Percentage of acknowledged alerts handled within 15m window")
    missed_checkins_today: int = Field(..., description="Count of missed expected submissions today")
    window_days: int = Field(7, description="Rolling window in days used for ack_rate_15min calculation")
