"""
WhatsApp click-to-chat QR code for a hospital's number.

Encodes a wa.me link with a pre-filled greeting. Scanned with a phone camera, it
opens WhatsApp on a chat with the hospital, which also opens the 24-hour window
in which the hospital may reply with free text.
"""

import base64
import io
import urllib.parse
from typing import Tuple

import qrcode

from app.services.whatsapp import normalize_phone


def build_whatsapp_url(phone_e164: str, prefilled_message: str) -> str:
    """Official WhatsApp click-to-chat URL."""
    return f"https://wa.me/{normalize_phone(phone_e164)}?text={urllib.parse.quote(prefilled_message)}"


def generate_whatsapp_qr_code(
    phone_e164: str,
    prefilled_message: str,
    fill_color: str = "#0F6E56",
    back_color: str = "white",
) -> Tuple[str, str]:
    """Return (wa.me URL, PNG data URL of a QR code encoding it)."""
    wa_url = build_whatsapp_url(phone_e164, prefilled_message)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(wa_url)
    qr.make(fit=True)

    buffer = io.BytesIO()
    qr.make_image(fill_color=fill_color, back_color=back_color).save(buffer, format="PNG")
    return wa_url, f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
