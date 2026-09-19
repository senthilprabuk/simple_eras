from datetime import datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

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

class AlertResolveResponse(BaseModel):
    alert_id: UUID
    status: str
    outcome: Outcome
    outcome_note: Optional[str] = None
    acknowledged_at: datetime
    resolved_at: datetime
    resolved_by: UUID
    resolved_by_name: str
