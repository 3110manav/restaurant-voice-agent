"""WhatsApp Cloud API: sending messages, and reading what Meta sends back to our webhook.

Needs WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID. Free-form messages and buttons only reach someone
inside WhatsApp's 24-hour service window; outside it Meta answers 131047, which the outbox records as
a permanent failure. Reaching people who have never messaged us needs approved templates (pilot work).
"""
import hashlib
import hmac
import os

import httpx

_TIMEOUT = 15.0
_PERMANENT_CODES = {131047, 131026, 131030, 131051, 132000, 132001}


class WhatsAppError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def is_configured() -> bool:
    return bool(os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_NUMBER_ID"))


def _base_url() -> str:
    version = os.environ.get("WHATSAPP_API_VERSION", "v23.0")
    return f"https://graph.facebook.com/{version}/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"}


def _checked(response: httpx.Response) -> dict:
    if response.is_success:
        return response.json()
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    code = error.get("code")
    details = (error.get("error_data") or {}).get("details") or error.get("message") or response.text[:200]
    retryable = response.status_code >= 500 or response.status_code == 429 or code not in _PERMANENT_CODES
    raise WhatsAppError(f"{code or response.status_code}: {details}", retryable=retryable)


def _post_message(payload: dict) -> str:
    try:
        response = httpx.post(
            f"{_base_url()}/messages",
            headers=_headers(),
            json={"messaging_product": "whatsapp", "recipient_type": "individual", **payload},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppError(f"network: {exc}") from exc
    return _checked(response)["messages"][0]["id"]


def send_text(to: str, text: str) -> str:
    return _post_message({"to": to, "type": "text", "text": {"body": text}})


def send_buttons(to: str, text: str, buttons: list[dict]) -> str:
    """At most three buttons, each {"id", "title"} with a title of at most 20 characters."""
    return _post_message(
        {
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [{"type": "reply", "reply": button} for button in buttons]
                },
            },
        }
    )


def send_image(to: str, png: bytes, caption: str) -> str:
    try:
        upload = httpx.post(
            f"{_base_url()}/media",
            headers=_headers(),
            data={"messaging_product": "whatsapp", "type": "image/png"},
            files={"file": ("payment-qr.png", png, "image/png")},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppError(f"network: {exc}") from exc
    media_id = _checked(upload)["id"]
    return _post_message({"to": to, "type": "image", "image": {"id": media_id, "caption": caption}})


# ------------------------------------------------------------------ webhook --


def signature_is_valid(raw_body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("WHATSAPP_APP_SECRET")
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def button_taps(payload: dict) -> list[dict]:
    """[{"sender", "button_id"}] for every button tap in a webhook payload."""
    return [
        {"sender": message.get("from", ""), "button_id": message["interactive"]["button_reply"]["id"]}
        for value in _values(payload)
        for message in value.get("messages", [])
        if message.get("type") == "interactive" and message.get("interactive", {}).get("type") == "button_reply"
    ]


def delivery_updates(payload: dict) -> list[dict]:
    """[{"wa_message_id", "status", "error"}] for every delivery report in a webhook payload."""
    updates = []
    for value in _values(payload):
        for status in value.get("statuses", []):
            errors = status.get("errors") or [{}]
            detail = errors[0].get("message") or errors[0].get("title")
            code = errors[0].get("code")
            updates.append(
                {
                    "wa_message_id": status.get("id"),
                    "status": status.get("status"),
                    "error": f"{code}: {detail}" if code or detail else None,
                }
            )
    return updates


def _values(payload: dict) -> list[dict]:
    return [
        change.get("value", {})
        for entry in payload.get("entry", [])
        for change in entry.get("changes", [])
    ]
