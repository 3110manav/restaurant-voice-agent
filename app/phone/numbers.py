"""Phone numbers arrive in many shapes: Exotel sends 09876543210, LiveKit +919876543210, a person says
ten digits. Everything is compared in one form, and WhatsApp only gets numbers that can be mobiles."""
import re


def _digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def canonical(raw: str | None) -> str | None:
    """+91 form, for matching a dialled number to its store. Landlines are valid here."""
    digits = _digits(raw).lstrip("0")
    if len(digits) == 10:
        return f"+91{digits}"
    return f"+{digits}" if len(digits) >= 11 else None


def whatsapp_number(raw: str | None) -> str | None:
    """Digits with country code, as WhatsApp wants them, or None if this can't be an Indian mobile."""
    digits = _digits(raw).lstrip("0")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    return None


def last_four(raw: str | None) -> str:
    return _digits(raw)[-4:]
