"""Sending WhatsApp messages through Meta's Cloud API, and logging each one.

    POST https://graph.facebook.com/{version}/{phone_number_id}/messages
         Authorization: Bearer <token>

Three kinds are used:
  text      a free-form reply. Only allowed inside the customer's 24-hour window (they messaged first).
  template  a pre-approved message, the only way to START a conversation (an order alert to the owner,
            a confirmation to a caller). See app/whatsapp/templates.md for the wording to submit.
  image     a received photo passed on by its media id (a prescription going to the pharmacist).

With no access token configured nothing is sent: the message is logged with status "logged" and the
caller carries on, so the whole flow can be developed and demoed before the Meta account is ready.
"""
import logging
import os
import re

import httpx

from app.whatsapp import channels
from app.whatsapp.channels import Channel

logger = logging.getLogger("sarthi.whatsapp")

GRAPH = "https://graph.facebook.com"
TEMPLATE_LANGUAGE = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")

_http: httpx.Client | None = None


class WhatsAppError(Exception):
    pass


def _client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=15.0)
    return _http


def graph_version() -> str:
    return os.environ.get("WHATSAPP_GRAPH_VERSION", "v21.0")


def token_for(channel: Channel) -> str | None:
    return os.environ.get(channel.token_env) or None


def clean_param(value: str, limit: int = 300) -> str:
    """Template variables can't hold newlines, tabs or runs of spaces."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else (text or "-")


def _to(number: str) -> str:
    return number.lstrip("+")  # the API wants digits only


def _post(channel: Channel, payload: dict) -> str | None:
    """Send one message payload; returns Meta's message id. Raises WhatsAppError on a rejection."""
    url = f"{GRAPH}/{graph_version()}/{channel.phone_number_id}/messages"
    response = _client().post(
        url, json={"messaging_product": "whatsapp", **payload}, headers={"Authorization": f"Bearer {token_for(channel)}"}
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {})
            message = f"{detail.get('code')}: {detail.get('message')}"
        except Exception:
            message = response.text[:200]
        raise WhatsAppError(message)
    messages = response.json().get("messages") or [{}]
    return messages[0].get("id")


def _deliver(
    channel: Channel, to: str, kind: str, payload: dict, summary: str, order_id: str | None = None
) -> str | None:
    """Send (or, with no token, just log) and record the outcome. Never raises: a WhatsApp failure
    must not break an order that is already placed."""
    status, error, message_id = "logged", None, None
    if token_for(channel):
        try:
            message_id = _post(channel, {"to": _to(to), **payload})
            status = "sent"
        except Exception as exc:
            status, error = "failed", str(exc)
            logger.warning("whatsapp %s to ...%s failed: %s", kind, to[-4:], error)
    else:
        logger.info("whatsapp not configured (no %s): would send %s to ...%s", channel.token_env, kind, to[-4:])
    channels.log_message(
        channel, channel.restaurant_id, "out", to, kind, summary, status, wa_message_id=message_id,
        order_id=order_id, error=error,
    )
    return message_id


def send_text(channel: Channel, to: str, body: str, order_id: str | None = None) -> str | None:
    return _deliver(channel, to, "text", {"type": "text", "text": {"body": body[:4000]}}, body, order_id)


def send_template(
    channel: Channel, to: str, name: str, params: list[str], order_id: str | None = None
) -> str | None:
    components = [{"type": "body", "parameters": [{"type": "text", "text": clean_param(p)} for p in params]}]
    payload = {"type": "template", "template": {"name": name, "language": {"code": TEMPLATE_LANGUAGE}, "components": components}}
    return _deliver(channel, to, "template", payload, f"[{name}] " + " | ".join(clean_param(p, 80) for p in params), order_id)


def send_image_by_id(channel: Channel, to: str, media_id: str, caption: str, order_id: str | None = None) -> str | None:
    """Pass on a photo that arrived in a webhook, by its media id (no download needed)."""
    payload = {"type": "image", "image": {"id": media_id, "caption": caption[:1000]}}
    return _deliver(channel, to, "image", payload, f"[image] {caption}", order_id)
