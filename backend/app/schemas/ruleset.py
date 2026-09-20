from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.services.scoring_config import Direction

class RulesetSummary(BaseModel):
    ruleset_id: int
    procedure_code: str
    procedure_name: str
    version: str
    status: str
    review_at: int
    critical_at: int
    max_points_per_parameter: int
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None
    parameter_count: int
    episodes_using: int

class RulesetParameter(BaseModel):
    code: str
    name: str
    type: str
    unit: Optional[str] = None
    section: str
    display_order: int
    collect_from_day: int
    collect_to_day: int
    score_from_day: int
    score_to_day: int
    weight: int
    is_mandatory: bool
    is_emergency: bool
    question_text: Optional[str] = None
    scoring_summary: str
    direction: Optional[Direction] = None
    scoring_config: Dict[str, Any]

class RulesetDetail(RulesetSummary):
    observation_days: int
    composite_summary: List[str] = []
    parameters: List[RulesetParameter]
