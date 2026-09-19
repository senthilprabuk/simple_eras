from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class LoginRequest(BaseModel):
    """
    Credentials for hospital admin login.
    hospital_id is optional and serves as a disambiguator when the same email
    and password are registered at more than one hospital.
    """
    email: str = Field(..., max_length=320, description="Admin user email address")
    # bcrypt only reads the first 72 bytes; the cap stops oversized payloads.
    password: str = Field(..., min_length=1, max_length=256, description="Admin password")
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
    expires_in: int = Field(..., description="Token lifetime in seconds")
    admin_user_id: UUID
    hospital_id: Optional[int] = Field(None, description="Null for an app admin, who belongs to no hospital")
    hospital_name: Optional[str] = None
    full_name: str
    role: str
