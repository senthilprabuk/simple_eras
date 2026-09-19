from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class WeeklyAlerts(BaseModel):
    week_start: date
    counts: Dict[str, int] = Field(..., description="Alerts raised that week, by tier")

class WeeklyAcknowledgement(BaseModel):
    week_start: date
    decided: int
    met: int
    pct: Optional[float] = None

class DailyAdherence(BaseModel):
    date: date
    expected: int
    submitted: int
    pct: Optional[float] = None

class ReportSummary(BaseModel):
    alerts_raised: int
    escalated: int
    median_ack_secs: Optional[int] = None
    ack_compliance_pct: Optional[float] = None
    adherence_pct: Optional[float] = None

class ReportResponse(BaseModel):
    days: int
    ack_window_secs: int
    summary: ReportSummary
    alerts_by_week: List[WeeklyAlerts]
    ack_by_week: List[WeeklyAcknowledgement]
    outcomes: Dict[str, int]
    adherence_by_day: List[DailyAdherence]
