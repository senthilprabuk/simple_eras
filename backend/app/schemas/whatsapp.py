"""
Schemas for WhatsApp Business Account management and QR code pairing.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WhatsAppAccountResponse(BaseModel):
    account_id: UUID
    hospital_id: int
    display_name: str
    display_phone_number: str
    phone_number_id: str
    waba_id: str
    meta_app_id: Optional[str] = None
    access_token_masked: str
    verify_token: str
    health_status: str
    is_active: bool
    qr_code_url: str = Field(..., description="Base64 PNG Data URL of WhatsApp click-to-chat QR code")
    click_to_chat_url: str = Field(..., description="Direct wa.me link")
    webhook_url: str = Field(..., description="Webhook callback URL to enter into Meta Developer Dashboard")
    created_at: datetime


class WhatsAppAccountCreate(BaseModel):
    display_phone_number: Optional[str] = Field(None, description="WhatsApp Business phone number in E.164 format, e.g. +91 98765 43210")
    display_name: Optional[str] = Field(None, description="Helpline or hospital display name")
    phone_number_id: str = Field(..., min_length=5, description="Meta Phone Number ID")
    waba_id: str = Field(..., min_length=5, description="Meta WhatsApp Business Account ID")
    access_token: Optional[str] = Field(None, description="Permanent System User Token (leave empty to keep existing)")
    verify_token: str = Field(..., min_length=3, description="Custom Webhook Verification Secret")
    meta_app_id: Optional[str] = Field(None, description="Optional Meta App ID")


class WhatsAppTestSendRequest(BaseModel):
    to_phone: str = Field(..., description="Recipient phone number in E.164 format, e.g. +919876543210")
    message: Optional[str] = Field(None, description="Optional custom test text")


class WhatsAppTestSendResponse(BaseModel):
    status: str
    message_id: Optional[str] = None
    error: Optional[str] = None
