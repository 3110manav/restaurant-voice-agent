"""Sends queued WhatsApp messages, with retries.

The voice worker sends right after an order is saved, so messages go out during the call. The API
also runs `run_forever`, which picks up whatever is left: retries, messages queued before WhatsApp
was configured, and anything a crashed sender left half done.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from app.phone import repository, upi, whatsapp

logger = logging.getLogger("sarthi.phone.outbox")

MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = [10, 30, 60, 300]
_STALE_AFTER = timedelta(minutes=2)
POLL_SECONDS = 10


def _send(message: dict) -> str:
    to, body = message["recipient"], message["body"]
    if body["type"] == "text":
        return whatsapp.send_text(to, body["text"])
    if body["type"] == "buttons":
        return whatsapp.send_buttons(to, body["text"], body["buttons"])
    if body.get("text_first"):
        whatsapp.send_text(to, body["text_first"])
    return whatsapp.send_image(to, upi.qr_png(body["upi_uri"]), body["caption"])


def _warn_owner_bill_failed(message: dict) -> None:
    """The customer thinks a bill is on its way, and only a person can sort it out now."""
    order = repository.get_order(message["order_id"])
    store = repository.get_store(order["store_id"]) if order else None
    if store:
        text = (
            f"Order {order['payment_ref']}: the bill couldn't reach the customer on WhatsApp. "
            f"Please call {order['customer_phone']} and share the payment details."
        )
        repository.queue_message(store["owner_whatsapp"], "owner_note", {"type": "text", "text": text}, order["id"], order.get("call_id"))


def _deliver(message: dict) -> None:
    if not repository.claim_message(message):
        return
    attempts = message["attempts"] + 1
    try:
        wa_id = _send(message)
    except Exception as exc:
        retryable = getattr(exc, "retryable", True) and attempts < MAX_ATTEMPTS
        logger.warning("message %s (%s) failed, attempt %s: %s", message["id"], message["kind"], attempts, exc)
        fields = {"status": "pending" if retryable else "failed", "last_error": str(exc)[:500]}
        if retryable:
            delay = _BACKOFF_SECONDS[min(attempts - 1, len(_BACKOFF_SECONDS) - 1)]
            fields["next_attempt_at"] = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        repository.update_message(message["id"], **fields)
        if not retryable and message["kind"] == "customer_bill":
            _warn_owner_bill_failed(message)
        return
    repository.update_message(
        message["id"], status="sent", wa_message_id=wa_id, sent_at=repository.now_iso(), last_error=None
    )


def flush() -> int:
    """Send everything that's due; returns how many were attempted. Waits, without using up any
    attempts, while WhatsApp isn't configured."""
    if not whatsapp.is_configured():
        return 0
    stale_before = (datetime.now(timezone.utc) - _STALE_AFTER).isoformat()
    due = repository.due_messages(stale_before)
    for message in due:
        _deliver(message)
    return len(due)


def flush_in_background() -> None:
    """Never makes the caller wait on WhatsApp. A failure here is retried by the API's loop."""

    def run() -> None:
        try:
            flush()
        except Exception:
            logger.exception("immediate send failed; the retry loop will pick it up")

    threading.Thread(target=run, daemon=True).start()


def run_forever(stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    complained = False
    while not stop.is_set():
        try:
            flush()
            complained = False
        except repository.NotConfiguredError:
            return  # no database: nothing can ever be queued
        except Exception:
            if not complained:  # e.g. the migration hasn't been run yet; once is enough
                logger.exception("couldn't process the message queue")
                complained = True
        if stop.wait(POLL_SECONDS):
            return


def start() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), daemon=True).start()
    return stop


def send_alert_now(recipient: str, text: str) -> bool:
    """Last resort when the database itself is down, so the store still hears about the customer."""
    try:
        whatsapp.send_text(recipient, text)
        return True
    except Exception:
        logger.exception("couldn't send the emergency alert")
        return False
