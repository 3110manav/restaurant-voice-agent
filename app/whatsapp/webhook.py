"""The webhook Meta calls for every message sent to a store's WhatsApp number.

  GET  /whatsapp/webhook   Meta's one-time handshake when you register the URL: echo hub.challenge back
                           if hub.verify_token matches WHATSAPP_VERIFY_TOKEN.
  POST /whatsapp/webhook   An event. Its X-Hub-Signature-256 header is an HMAC of the raw body with the app
                           secret (WHATSAPP_APP_SECRET); anything unsigned or wrongly signed is rejected,
                           so nobody can post fake customer messages. (Local testing without Meta can set
                           WHATSAPP_ALLOW_UNSIGNED=1.)

Meta expects a fast 200 and retries on a slow answer, so the agent runs in a background task, and each
message id is processed once however many times Meta sends it.
"""
import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.customers.phone import normalize_phone
from app.menu import repository
from app.whatsapp import channels, client, inbound

logger = logging.getLogger("sarthi.whatsapp")
router = APIRouter(prefix="/whatsapp")


def valid_signature(raw_body: bytes, header: str | None, secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


@router.get("/webhook")
def verify(request: Request) -> PlainTextResponse:
    params = request.query_params
    token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if params.get("hub.mode") == "subscribe" and token and hmac.compare_digest(params.get("hub.verify_token", ""), token):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> dict:
    raw = await request.body()
    secret = os.environ.get("WHATSAPP_APP_SECRET")
    if secret:
        if not valid_signature(raw, request.headers.get("x-hub-signature-256"), secret):
            raise HTTPException(status_code=401, detail="bad signature")
    elif os.environ.get("WHATSAPP_ALLOW_UNSIGNED") != "1":
        raise HTTPException(status_code=503, detail="WHATSAPP_APP_SECRET is not set")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid JSON") from None
    background.add_task(process_payload, payload)
    return {"status": "ok"}


def process_payload(payload: dict) -> None:
    """Handle every message in one webhook delivery. Never raises: Meta must always get its 200 and a
    bad message must not stop the others."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            for message in value.get("messages", []):
                try:
                    process_message(phone_number_id, message)
                except Exception:
                    logger.exception("couldn't process whatsapp message %s", message.get("id"))
            for status in value.get("statuses", []):
                if status.get("status") == "failed":
                    logger.warning("whatsapp delivery failed: %s", (status.get("errors") or [{}])[0])


def process_message(phone_number_id: str | None, message: dict) -> None:
    channel = channels.channel_by_phone_number_id(phone_number_id) if phone_number_id else None
    if channel is None:
        logger.warning("message for an unknown whatsapp number id %s", phone_number_id)
        return
    store = repository.get_restaurant(channel.restaurant_id)
    if store is None or store.get("status") != "live":
        return
    phone = normalize_phone(message.get("from"))
    if phone is None:
        return
    kind = message.get("type", "text")
    media_id = (message.get(kind) or {}).get("id") if kind in ("image", "document") else None
    text = (message.get("text") or {}).get("body", "") if kind == "text" else (message.get(kind) or {}).get("caption", "")
    logged = f"media:{media_id}|{text}" if media_id else text
    if not channels.log_message(channel, store["id"], "in", phone, kind, logged, "received", wa_message_id=message.get("id")):
        return  # Meta retried a message we already handled

    if kind == "text":
        command = inbound.parse_command(text)
        if command and phone in channel.staff():
            reply = inbound.staff_command(channel, store, phone, command)
        else:
            reply = inbound.reply_to_text(store, phone, text)
    elif kind in ("image", "document"):
        if phone in channel.staff():
            return  # staff photos are theirs to send on; only customers' photos are prescriptions
        reply = inbound.handle_media(channel, store, phone, media_id, text)
    else:
        reply = inbound.lang.line("en", "wa_unsupported")
    client.send_text(channel, phone, reply)
