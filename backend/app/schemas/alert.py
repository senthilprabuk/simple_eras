from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from app.schemas.dashboard import Reason
from app.schemas.episode import OperativeSide

# Mirrors the alert_outcome_known constraint on txn.alert.
Outcome = Literal["reassured", "plan_adjusted", "same_day_review", "emergency"]

class AlertAcknowledgeResponse(BaseModel):
    """Response returned when an admin successfully acknowledges an alert."""
    alert_id: UUID
    status: str
    acknowledged_at: datetime
    acknowledged_by: UUID
    acknowledged_by_name: str

class AlertResolveRequest(BaseModel):
    """Every resolved alert must carry a clinical outcome; the note is optional."""
    outcome: Outcome
    note: Optional[str] = Field(None, max_length=2000)

    @field_validator("note")
    @classmethod
    def blank_note_is_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

class AlertHistoryItem(BaseModel):
    """An alert in any state, with who handled it and how quickly."""
    alert_id: UUID
    episode_id: UUID
    patient_name: str
    mrn: Optional[str] = None
    phone_e164: Optional[str] = Field(
        None, description="The patient's own number, so an emergency can be answered without leaving the list")
    operative_side: Optional[OperativeSide] = Field(
        None, description="Which knee was replaced; null for episodes enrolled before it was captured")
    procedure_code: str = Field(..., description="Composed with the side for display, so a hip never reads as a TKR")
    tier: str
    status: str
    day_after_discharge: int
    reasons: List[Reason]
    raised_at: datetime
    escalated_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_name: Optional[str] = None
    ack_secs: Optional[int] = Field(None, description="Seconds from raised to acknowledged")
    ack_window_secs: int
    resolved_at: Optional[datetime] = None
    resolved_by_name: Optional[str] = None
    outcome: Optional[Outcome] = None
    outcome_note: Optional[str] = None

    @field_validator("reasons", mode="before")
    @classmethod
    def plain_strings_become_reasons(cls, value):
        return [{"name": r, "detail": r} if isinstance(r, str) else r for r in value]

class AlertHistoryResponse(BaseModel):
    items: List[AlertHistoryItem]
    total: int
    limit: int
    offset: int

class AlertResolveResponse(BaseModel):
    alert_id: UUID
    status: str
    outcome: Outcome
    outcome_note: Optional[str] = None
    acknowledged_at: datetime
    resolved_at: datetime
    resolved_by: UUID
    resolved_by_name: str
