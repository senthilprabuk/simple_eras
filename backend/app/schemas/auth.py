from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

class LoginRequest(BaseModel):
    """
    Credentials for hospital admin login.
    hospital_id is optional and serves as a disambiguator when the same email
    exists across multiple hospitals.
    """
    email: str = Field(..., description="Admin user email address")
    password: str = Field(..., min_length=6, description="Admin password")
    hospital_id: Optional[int] = Field(None, description="Optional hospital ID to disambiguate email")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned:
            raise ValueError("Invalid email format")
        return cleaned

class TokenResponse(BaseModel):
    """JWT response after successful login."""
    access_token: str
    token_type: str = "bearer"
    admin_user_id: UUID
    hospital_id: int
    full_name: str
    role: str
