from datetime import datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

Role = Literal["admin", "superadmin"]

class Clinician(BaseModel):
    admin_user_id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime

class ClinicianCreate(BaseModel):
    email: str = Field(..., max_length=320)
    full_name: str = Field(..., min_length=1, max_length=200)
    role: Role = "admin"
    password: str = Field(..., min_length=12, max_length=256, description="Temporary password to share with the clinician")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email format")
        return value

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

class ClinicianUpdate(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)

    @model_validator(mode="after")
    def must_change(self):
        if self.new_password == self.current_password:
            raise ValueError("new password must differ from the current one")
        return self
