"""
WhatsApp Click-to-Chat QR Code generator.

Encodes an official wa.me click-to-chat link with a pre-filled greeting message.
When scanned with any smartphone camera, WhatsApp opens directly to the hospital's
verified chat thread.
"""

import base64
import io
import re
import urllib.parse
from typing import Dict, Tuple

import qrcode


def clean_phone_digits(phone: str) -> str:
    """Strip all non-digit characters from phone number."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def build_whatsapp_url(phone_e164: str, prefilled_message: str = "Hello from St. Mary's ERAS Patient") -> str:
    """Build official WhatsApp click-to-chat URL."""
    digits = clean_phone_digits(phone_e164)
    encoded = urllib.parse.quote(prefilled_message)
    return f"https://wa.me/{digits}?text={encoded}"


def generate_whatsapp_qr_code(
    phone_e164: str,
    prefilled_message: str = "Hello from St. Mary's ERAS Patient",
    fill_color: str = "#0F6E56",
    back_color: str = "white",
) -> Tuple[str, str]:
    """
    Generate a PNG QR code encoding the WhatsApp click-to-chat URL.
    Returns (wa_url, base64_png_data_url).
    """
    wa_url = build_whatsapp_url(phone_e164, prefilled_message)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(wa_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    return wa_url, data_url
