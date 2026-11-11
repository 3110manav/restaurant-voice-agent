"""Phone numbers as the key a customer is recognised by: always E.164 (+919876543210)."""
import re

_INDIAN_MOBILE_START = "6789"


def normalize_phone(raw: str | None) -> str | None:
    """`raw` as an E.164 number, or None when it isn't a usable phone number.

    Handles how Indian numbers actually arrive: caller ID from a telecom ("09876543210",
    "+919876543210", "919876543210"), a typed ten-digit mobile, or an already international
    number (kept as is). Anything else, such as a withheld or malformed number, is None.
    """
    if not raw:
        return None
    text = raw.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 and digits[0] != "0" else None
    if digits.startswith("00"):
        digits = digits[2:]
        return f"+{digits}" if 8 <= len(digits) <= 15 and digits[:1] != "0" else None
    if len(digits) == 10 and digits[0] in _INDIAN_MOBILE_START:
        return f"+91{digits}"
    if len(digits) == 11 and digits[0] == "0" and digits[1] in _INDIAN_MOBILE_START:
        return f"+91{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91") and digits[2] in _INDIAN_MOBILE_START:
        return f"+{digits}"
    return None


def mask_phone(phone: str | None) -> str:
    """For logs: never write a full customer number to them."""
    if not phone or len(phone) < 8:
        return "unknown"
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
