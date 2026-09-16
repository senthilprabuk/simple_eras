from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class AlertAcknowledgeResponse(BaseModel):
    """Response returned when an admin successfully acknowledges an alert."""
    alert_id: UUID
    status: str = "acknowledged"
    acknowledged_at: datetime
    acknowledged_by: UUID
    acknowledged_by_name: Optional[str] = None
    message: str = "Alert successfully acknowledged"
