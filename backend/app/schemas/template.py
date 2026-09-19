import re
from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

TemplateKey = Literal["enrollment_welcome", "checkin_reminder", "missed_checkin", "urgent_guidance"]
TemplateLanguage = Literal["en", "ta", "hi"]

# Everything the sender can fill in. Anything else in braces is rejected, so a
# typo never reaches a patient as literal "{patient_frist_name}".
PLACEHOLDERS: Dict[str, str] = {
    "patient_first_name": "The patient's first name",
    "hospital_name": "Your hospital's name",
    "post_op_day": "Days since discharge",
    "checkin_link": "Link to the patient's daily check-in",
}

TEMPLATE_PURPOSES: Dict[str, str] = {
    "enrollment_welcome": "Sent once, when a patient is enrolled",
    "checkin_reminder": "Sent each morning the check-in opens",
    "missed_checkin": "Sent when a check-in has not arrived by the end of the day",
    "urgent_guidance": "Sent straight after a patient reports an emergency symptom",
}

PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]*)\}")

class TemplateEntry(BaseModel):
    template_key: TemplateKey
    language_code: TemplateLanguage
    body: Optional[str] = Field(None, description="Null when not written for this language yet")
    is_active: bool = False
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None

class TemplateCatalogue(BaseModel):
    templates: List[TemplateEntry]
    purposes: Dict[str, str]
    placeholders: Dict[str, str]

class TemplateUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=1024)
    is_active: bool = True

    @field_validator("body")
    @classmethod
    def known_placeholders_only(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        if value.count("{") != value.count("}"):
            raise ValueError("has an unmatched brace")
        unknown = sorted({name for name in PLACEHOLDER_PATTERN.findall(value) if name not in PLACEHOLDERS})
        if unknown:
            raise ValueError(f"uses unknown placeholders: {', '.join('{' + n + '}' for n in unknown)}")
        return value
